#!/usr/bin/env python3
"""Utilidades de depuración para login Coupa con Selenium.

Objetivo: aislar y probar las recomendaciones para evitar loops post-captcha:
- Verificación de sesión *pasiva* (sin navegación lateral).
- Resolución de captcha con cooldown por (URL, sitekey).
- Click en botones de sesión con selectores más estrictos.
- Esperas explícitas por transición (URL/DOM), evitando sleeps ciegos.
- Snapshot de diagnóstico (screenshot + HTML) ante no-transición.
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

COUPA_BASE = "https://supplier.coupahost.com"
LOGIN_URL = f"{COUPA_BASE}/sessions/new"
DASHBOARD_URL = f"{COUPA_BASE}/dashboard"
PRIVATE_EVENTS_URL = f"{COUPA_BASE}/quotes/private_events/"

logger = logging.getLogger("coupa_auth_debug")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


@dataclass
class CaptchaState:
    signature: Optional[tuple[str, str]] = None
    solved_at: float = 0.0
    token: Optional[str] = None


@dataclass
class CoupaAuthDebugger:
    driver: webdriver.Chrome
    twocaptcha_key: str
    captcha_cooldown_sec: int = 120
    wait_sec: int = 20
    debug_dir: Path = field(default_factory=lambda: Path("debug_artifacts"))
    captcha_state: CaptchaState = field(default_factory=CaptchaState)

    def __post_init__(self) -> None:
        self.debug_dir.mkdir(parents=True, exist_ok=True)

    # -------------------------
    # Sesión: check pasivo
    # -------------------------
    def is_logged_in_passive(self) -> bool:
        """Verifica sesión sin navegar ni mutar estado del flujo."""
        try:
            current_url = self.driver.current_url.lower()
            if any(x in current_url for x in ["sessions/new", "login", "max_concurrent"]):
                return False

            strong_logged_signals = [
                "//a[contains(@href, '/sessions/logout')]",
                "//div[contains(@class, 'user-menu')]",
                "//a[contains(@href, '/quotes/private_events')]",
            ]
            for xp in strong_logged_signals:
                if self.driver.find_elements(By.XPATH, xp):
                    return True

            return "supplier.coupahost.com" in current_url and "sessions" not in current_url
        except Exception:
            return False

    # -------------------------
    # Captcha
    # -------------------------
    def detect_site_key(self) -> Optional[str]:
        rec = self.driver.find_elements(By.CLASS_NAME, "g-recaptcha")
        if rec:
            key = rec[0].get_attribute("data-sitekey")
            if key:
                return key

        for frame in self.driver.find_elements(By.XPATH, "//iframe[contains(@src, 'recaptcha')]"):
            src = frame.get_attribute("src") or ""
            m = re.search(r"[?&]k=([^&]+)", src)
            if m:
                return m.group(1)
        return None

    def solve_captcha(self, site_key: str, page_url: str) -> Optional[str]:
        if not self.twocaptcha_key:
            logger.warning("TWOCAPTCHA_API_KEY no configurada.")
            return None

        payload = {
            "key": self.twocaptcha_key,
            "method": "userrecaptcha",
            "googlekey": site_key,
            "pageurl": page_url,
            "json": 1,
        }
        try:
            submit = requests.post("http://2captcha.com/in.php", data=payload, timeout=30).json()
            if submit.get("status") != 1:
                logger.error("2Captcha submit error: %s", submit.get("request"))
                return None

            task_id = submit["request"]
            for _ in range(24):
                time.sleep(5)
                result = requests.get(
                    "http://2captcha.com/res.php",
                    params={"key": self.twocaptcha_key, "action": "get", "id": task_id, "json": 1},
                    timeout=30,
                ).json()
                if result.get("status") == 1:
                    return result.get("request")
                if result.get("request") != "CAPCHA_NOT_READY":
                    logger.error("2Captcha get error: %s", result.get("request"))
                    return None
        except Exception as exc:
            logger.error("Error solve_captcha: %s", exc)
        return None

    def handle_captcha_once(self) -> bool:
        site_key = self.detect_site_key()
        if not site_key:
            return False

        signature = (self.driver.current_url.split("?")[0], site_key)
        now = time.time()
        if self.captcha_state.signature == signature and (now - self.captcha_state.solved_at) < self.captcha_cooldown_sec:
            logger.info("Captcha ya resuelto recientemente en esta pantalla; se omite nuevo envío.")
            return True

        logger.info("Captcha detectado. Resolviendo para URL=%s", signature[0])
        token = self.solve_captcha(site_key, self.driver.current_url)
        if not token:
            return False

        self.driver.execute_script(
            """
            const token = arguments[0];
            const target = document.querySelector('#g-recaptcha-response') || document.querySelector('[name="g-recaptcha-response"]');
            if (target) {
                target.style.display = 'block';
                target.value = token;
                target.dispatchEvent(new Event('input', { bubbles: true }));
                target.dispatchEvent(new Event('change', { bubbles: true }));
            }
            """,
            token,
        )
        self.captcha_state = CaptchaState(signature=signature, solved_at=now, token=token)
        return True

    # -------------------------
    # Interacción robusta
    # -------------------------
    def click_session_continue_button(self) -> bool:
        """Busca botón de sesión concurrente con selectores más concretos."""
        strict_candidates = [
            (By.CSS_SELECTOR, "button.s-login"),
            (By.CSS_SELECTOR, "button[data-testid*='session' i]"),
            (By.XPATH, "//button[contains(@class,'s-login') and (contains(.,'Login') or contains(.,'Acessar') or contains(.,'Entrar'))]"),
            (By.XPATH, "//button[contains(.,'entrar nesta sessão') or contains(.,'Continuar')]"),
        ]

        for by, sel in strict_candidates:
            elems = self.driver.find_elements(by, sel)
            for el in elems:
                if el.is_displayed() and el.is_enabled():
                    self.driver.execute_script("arguments[0].click();", el)
                    logger.info("Click sesión con selector: %s=%s", by, sel)
                    return True
        return False

    def wait_for_transition(self, timeout: Optional[int] = None) -> bool:
        timeout = timeout or self.wait_sec

        def transitioned(d: webdriver.Chrome) -> bool:
            url = d.current_url.lower()
            if any(k in url for k in ["/dashboard", "/quotes/private_events"]):
                return True
            if d.find_elements(By.XPATH, "//a[contains(@href, '/sessions/logout')]"):
                return True
            return False

        try:
            WebDriverWait(self.driver, timeout).until(transitioned)
            return True
        except TimeoutException:
            return False

    def dump_debug_snapshot(self, tag: str) -> None:
        stamp = int(time.time())
        png = self.debug_dir / f"{tag}_{stamp}.png"
        html = self.debug_dir / f"{tag}_{stamp}.html"
        self.driver.save_screenshot(str(png))
        html.write_text(self.driver.page_source, encoding="utf-8")
        logger.info("Snapshot guardado: %s / %s", png, html)

    # -------------------------
    # Flujo de prueba
    # -------------------------
    def debug_login_transition(self) -> bool:
        """Flujo mínimo para depurar estancamiento post-captcha."""
        self.driver.get(LOGIN_URL)

        # 1) Intentar resolver captcha una sola vez por pantalla
        self.handle_captcha_once()

        # 2) Si estamos en sessions/new, intentar botón de continuar sesión
        current = self.driver.current_url.lower()
        if "sessions" in current:
            self.click_session_continue_button()

        # 3) Esperar transición real en vez de sleep fijo
        if self.wait_for_transition(timeout=self.wait_sec):
            logger.info("Transición post-login confirmada. URL=%s", self.driver.current_url)
            return True

        logger.error("Sin transición tras captcha/click. URL=%s", self.driver.current_url)
        self.dump_debug_snapshot("stuck_after_captcha")
        return False


def _build_driver(headless: bool = False) -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1440,900")
    return webdriver.Chrome(options=options)


def main() -> int:
    twocaptcha_key = os.getenv("TWOCAPTCHA_API_KEY", "")
    headless = os.getenv("HEADLESS", "0") in {"1", "true", "True"}
    driver = _build_driver(headless=headless)

    try:
        debugger = CoupaAuthDebugger(driver=driver, twocaptcha_key=twocaptcha_key)
        ok = debugger.debug_login_transition()
        logger.info("is_logged_in_passive=%s", debugger.is_logged_in_passive())
        return 0 if ok else 1
    finally:
        driver.quit()


if __name__ == "__main__":
    raise SystemExit(main())
