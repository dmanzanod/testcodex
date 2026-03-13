#!/usr/bin/env python3
"""RPA para acceder a https://www.me.com.br/ con Selenium WebDriver."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
import unicodedata
from typing import Iterable, Optional

from selenium import webdriver
from selenium.webdriver import ActionChains
from selenium.common.exceptions import (
    NoAlertPresentException,
    NoSuchElementException,
    SessionNotCreatedException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver import ChromeOptions
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE_URL = "https://www.me.com.br/"
LOGIN_URL = "https://me.com.br/do/Login.mvc/LoginNew"
DEFAULT_LOGIN = "FLSMIDTH23"
DEFAULT_PASSWORD = "FLSmidth23@23"


def build_driver(headless: bool) -> webdriver.Chrome:
    options = ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--window-size=1440,900")
    options.add_argument("--lang=pt-BR")

    chrome_binary = os.getenv("CHROME_BINARY")
    if chrome_binary:
        options.binary_location = chrome_binary

    service_kwargs = {}
    chromedriver_log = os.getenv("CHROMEDRIVER_LOG")
    if chromedriver_log:
        service_kwargs["log_output"] = chromedriver_log
    if os.getenv("CHROMEDRIVER_VERBOSE", "").lower() in {"1", "true", "yes"}:
        service_kwargs["service_args"] = ["--verbose"]

    service = Service(**service_kwargs)
    return webdriver.Chrome(service=service, options=options)


def find_first_visible(driver: webdriver.Chrome, selectors: Iterable[tuple[str, str]], timeout: int = 15):
    wait = WebDriverWait(driver, timeout)
    last_error: Optional[Exception] = None
    for by, selector in selectors:
        try:
            return wait.until(EC.visibility_of_element_located((by, selector)))
        except TimeoutException as exc:
            last_error = exc
    if last_error:
        raise last_error
    raise NoSuchElementException("No se encontraron selectores válidos")


def open_login_page(driver: webdriver.Chrome, timeout: int) -> None:
    driver.get(BASE_URL)
    WebDriverWait(driver, timeout).until(lambda d: d.execute_script("return document.readyState") == "complete")

    candidates = [
        (By.CSS_SELECTOR, "a[href*='login']"),
        (By.CSS_SELECTOR, "a[href*='Login']"),
        (By.XPATH, "//a[contains(translate(normalize-space(.), 'LOGINENTRAR', 'loginentrar'), 'login')]"),
        (By.XPATH, "//button[contains(translate(normalize-space(.), 'LOGINENTRAR', 'loginentrar'), 'login')]"),
    ]

    for by, selector in candidates:
        for element in driver.find_elements(by, selector):
            if element.is_displayed() and element.is_enabled():
                element.click()
                WebDriverWait(driver, timeout).until(lambda d: "LoginNew" in d.current_url or "login" in d.current_url.lower())
                return

    driver.get(LOGIN_URL)


def do_login(driver: webdriver.Chrome, login_name: str, password: str) -> None:
    username_input = find_first_visible(
        driver,
        [
            (By.ID, "LoginName"),
            (By.NAME, "LoginName"),
            (By.CSS_SELECTOR, "input[type='text']"),
            (By.CSS_SELECTOR, "input[name*='user' i]"),
            (By.CSS_SELECTOR, "input[name*='login' i]"),
        ],
    )
    username_input.clear()
    username_input.send_keys(login_name)

    password_input = find_first_visible(
        driver,
        [
            (By.ID, "RAWSenha"),
            (By.NAME, "RAWSenha"),
            (By.CSS_SELECTOR, "input[type='password']"),
            (By.CSS_SELECTOR, "input[name*='senha' i]"),
        ],
    )
    password_input.clear()
    password_input.send_keys(password)

    submit = find_first_visible(
        driver,
        [
            (By.CSS_SELECTOR, "button[type='submit']"),
            (By.CSS_SELECTOR, "input[type='submit']"),
            (By.XPATH, "//button[contains(., 'Entrar') or contains(., 'Acessar') or contains(., 'Login')]"),
        ],
    )
    submit.click()


def _looks_like_logged_area(driver: webdriver.Chrome) -> bool:
    url = driver.current_url.lower()
    if any(token in url for token in ["definetimezonebase", "timezone", "home", "dashboard", "comunicadousuario"]):
        return True

    menu_selectors = [
        (By.XPATH, "//*[contains(translate(normalize-space(.), 'TRANSAÇÕES', 'transações'), 'transações') or contains(translate(normalize-space(.), 'TRANSACCOES', 'transaccoes'), 'transaccoes')]"),
        (By.XPATH, "//*[contains(translate(normalize-space(.), 'COTAÇÃO', 'cotação'), 'cotação') or contains(translate(normalize-space(.), 'COTACAO', 'cotacao'), 'cotacao')]"),
        (By.CSS_SELECTOR, "img[src*='logo' i], .logo img, .navbar-brand img, #logo img"),
    ]

    for by, selector in menu_selectors:
        for element in driver.find_elements(by, selector):
            if element.is_displayed():
                return True

    return False


def validate_login(driver: webdriver.Chrome, timeout: int) -> None:
    try:
        WebDriverWait(driver, timeout).until(lambda d: _looks_like_logged_area(d))
    except TimeoutException as exc:
        raise TimeoutException(
            f"No se confirmó login. URL actual: {driver.current_url!r}. "
            "Si ya estás autenticado, ajusta los selectores/condiciones de validate_login()."
        ) from exc


def _click_any(driver: webdriver.Chrome, selectors: list[tuple[str, str]], timeout: int) -> bool:
    wait = WebDriverWait(driver, timeout)
    for by, selector in selectors:
        try:
            element = wait.until(EC.element_to_be_clickable((by, selector)))
            element.click()
            return True
        except TimeoutException:
            continue
    return False


def _click_any_with_frames(driver: webdriver.Chrome, selectors: list[tuple[str, str]], timeout_main: int = 5, timeout_frame: int = 2) -> bool:
    if _click_any(driver, selectors, timeout=timeout_main):
        return True

    for frame in driver.find_elements(By.CSS_SELECTOR, "iframe"):
        try:
            driver.switch_to.frame(frame)
            if _click_any(driver, selectors, timeout=timeout_frame):
                return True
        except Exception:
            pass
        finally:
            driver.switch_to.default_content()

    return False


def handle_timezone_screen(driver: webdriver.Chrome, timeout: int) -> None:
    if "timezone" not in driver.current_url.lower() and "DefineTimeZoneBase" not in driver.current_url:
        return

    action_selectors = [
        (By.XPATH, "//a[contains(translate(normalize-space(.), 'IGNORARECONTINUAR', 'ignorarecontinuar'), 'ignorar e continuar')]"),
        (By.XPATH, "//button[contains(translate(normalize-space(.), 'IGNORARECONTINUAR', 'ignorarecontinuar'), 'ignorar e continuar')]"),
        (By.XPATH, "//*[contains(translate(normalize-space(.), 'IGNOREANDCONTINUE', 'ignoreandcontinue'), 'ignore and continue')]"),
        (By.XPATH, "//*[normalize-space(text())='×']"),
        (By.CSS_SELECTOR, "button[title*='Fechar' i], button[aria-label*='fechar' i], .close, [data-dismiss='modal']"),
    ]

    clicked = _click_any(driver, action_selectors, timeout=3)

    if not clicked:
        for frame in driver.find_elements(By.CSS_SELECTOR, "iframe"):
            try:
                driver.switch_to.frame(frame)
                if _click_any(driver, action_selectors, timeout=2):
                    clicked = True
                    break
            except Exception:
                pass
            finally:
                driver.switch_to.default_content()

    if not clicked:
        return

    def timezone_closed(d: webdriver.Chrome) -> bool:
        if "timezone" not in d.current_url.lower() and "DefineTimeZoneBase" not in d.current_url:
            return True
        if d.find_elements(By.CSS_SELECTOR, "iframe[src*='TimezoneModal' i]"):
            return False
        close_candidates = [
            (By.XPATH, "//*[contains(translate(normalize-space(.), 'IGNORARECONTINUAR', 'ignorarecontinuar'), 'ignorar e continuar')]"),
            (By.CSS_SELECTOR, ".close, [data-dismiss='modal']"),
        ]
        for by, selector in close_candidates:
            for element in d.find_elements(by, selector):
                if element.is_displayed():
                    return False
        return True

    WebDriverWait(driver, timeout).until(timezone_closed)


def handle_confirmation_window(driver: webdriver.Chrome, timeout: int) -> None:
    confirmation_selectors = [
        (By.XPATH, "//button[normalize-space()='Sim' or normalize-space()='Si']"),
        (By.XPATH, "//a[normalize-space()='Sim' or normalize-space()='Si']"),
        (By.XPATH, "//*[contains(@class, 'btn') and (normalize-space()='Sim' or normalize-space()='Si')]"),
        (By.XPATH, "//button[contains(translate(normalize-space(.), 'SIMSIYES', 'simsiyes'), 'sim') or contains(translate(normalize-space(.), 'SIMSIYES', 'simsiyes'), 'si') or contains(translate(normalize-space(.), 'SIMSIYES', 'simsiyes'), 'yes')]"),
    ]

    clicked = _click_any(driver, confirmation_selectors, timeout=2)

    if not clicked:
        for frame in driver.find_elements(By.CSS_SELECTOR, "iframe"):
            try:
                driver.switch_to.frame(frame)
                if _click_any(driver, confirmation_selectors, timeout=1):
                    clicked = True
                    break
            except Exception:
                pass
            finally:
                driver.switch_to.default_content()

    if clicked:
        WebDriverWait(driver, timeout).until(lambda d: not d.find_elements(By.XPATH, "//button[normalize-space()='Sim' or normalize-space()='Si']"))


def handle_continue_navigation(driver: webdriver.Chrome, timeout: int) -> None:
    exact_button_id = "ctl00_conteudo_frmComunicadoUsuario_ButtonBar1_btn_ctl00_conteudo_frmComunicadoUsuario_ButtonBar1_btnContinuar"
    continue_selectors = [
        (By.ID, exact_button_id),
        (By.CSS_SELECTOR, "span#ctl00_conteudo_frmComunicadoUsuario_ButtonBar1_btnContinuar > button"),
        (By.XPATH, "//span[@id='ctl00_conteudo_frmComunicadoUsuario_ButtonBar1_btnContinuar']//button"),
        (By.XPATH, "//button[contains(normalize-space(.), 'Continuar Navegação')]"),
        (By.XPATH, "//button[contains(translate(normalize-space(.), 'CONTINUARNAVEGACAOÇÃ', 'continuarnavegacaoça'), 'continuar')]"),
        (By.XPATH, "//a[contains(translate(normalize-space(.), 'CONTINUARNAVEGACAOÇÃ', 'continuarnavegacaoça'), 'continuar')]"),
        (By.XPATH, "//input[((@type='button') or (@type='submit')) and contains(translate(@value, 'CONTINUARNAVEGACAOÇÃ', 'continuarnavegacaoça'), 'continuar')]"),
    ]

    if "comunicadousuario" not in driver.current_url.lower() and not _comunicado_continue_available(driver):
        return

    clicked = False
    start_url = driver.current_url

    for _ in range(3):
        if "comunicadousuario" in driver.current_url.lower():
            try:
                exact_btn = WebDriverWait(driver, 4).until(EC.presence_of_element_located((By.ID, exact_button_id)))
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", exact_btn)
                try:
                    WebDriverWait(driver, 2).until(EC.element_to_be_clickable((By.ID, exact_button_id))).click()
                except Exception:
                    driver.execute_script("arguments[0].click();", exact_btn)
                clicked = True
            except TimeoutException:
                pass

        if not clicked:
            clicked = _click_any(driver, continue_selectors, timeout=2)

        if not clicked:
            for frame in driver.find_elements(By.CSS_SELECTOR, "iframe"):
                try:
                    driver.switch_to.frame(frame)
                    if _click_any(driver, continue_selectors, timeout=1):
                        clicked = True
                        break
                except Exception:
                    pass
                finally:
                    driver.switch_to.default_content()

        if clicked:
            try:
                WebDriverWait(driver, 4).until(lambda d: d.current_url != start_url)
                break
            except TimeoutException:
                try:
                    alert = driver.switch_to.alert
                    alert.accept()
                except NoAlertPresentException:
                    pass
                clicked = False

    if not clicked:
        raise TimeoutException("No se pudo presionar 'Continuar Navegação'")

    WebDriverWait(driver, timeout).until(
        lambda d: d.current_url != start_url or "comunicadousuario" not in d.current_url.lower()
    )
    WebDriverWait(driver, timeout).until(lambda d: d.execute_script("return document.readyState") == "complete")

    try:
        alert = driver.switch_to.alert
        alert.accept()
    except NoAlertPresentException:
        pass


def _comunicado_continue_available(driver: webdriver.Chrome) -> bool:
    continue_selectors = [
        (By.ID, "ctl00_conteudo_frmComunicadoUsuario_ButtonBar1_btn_ctl00_conteudo_frmComunicadoUsuario_ButtonBar1_btnContinuar"),
        (By.CSS_SELECTOR, "span#ctl00_conteudo_frmComunicadoUsuario_ButtonBar1_btnContinuar > button"),
        (By.XPATH, "//button[contains(normalize-space(.), 'Continuar Navegação')]"),
    ]

    for by, selector in continue_selectors:
        for element in driver.find_elements(by, selector):
            if element.is_displayed():
                return True

    for frame in driver.find_elements(By.CSS_SELECTOR, "iframe"):
        try:
            driver.switch_to.frame(frame)
            for by, selector in continue_selectors:
                for element in driver.find_elements(by, selector):
                    if element.is_displayed():
                        return True
        except Exception:
            pass
        finally:
            driver.switch_to.default_content()

    return False


def go_to_transacoes_em_andamento(driver: webdriver.Chrome, timeout: int) -> None:
    logo_selectors = [
        (By.CSS_SELECTOR, "img[src*='logo' i]"),
        (By.CSS_SELECTOR, ".logo img, .navbar-brand img, #logo img"),
    ]

    for by, selector in logo_selectors:
        try:
            WebDriverWait(driver, 5).until(EC.presence_of_element_located((by, selector)))
            break
        except TimeoutException:
            continue

    time.sleep(3)

    transacoes_selectors = [
        (By.XPATH, "//a[contains(translate(normalize-space(.), 'TRANSAÇÕES', 'transações'), 'transações') or contains(translate(normalize-space(.), 'TRANSACCOES', 'transaccoes'), 'transaccoes')]"),
        (By.XPATH, "//button[contains(translate(normalize-space(.), 'TRANSAÇÕES', 'transações'), 'transações') or contains(translate(normalize-space(.), 'TRANSACCOES', 'transaccoes'), 'transaccoes')]"),
        (By.XPATH, "//*[self::a or self::button or self::span][contains(translate(normalize-space(.), 'TRANSACOESTRANSACÇÕES', 'transacoestransacções'), 'transac')]"),
    ]

    em_andamento_selectors = [
        (By.XPATH, "//a[contains(translate(normalize-space(.), 'EMANDAMENTO', 'emandamento'), 'em andamento')]"),
        (By.XPATH, "//button[contains(translate(normalize-space(.), 'EMANDAMENTO', 'emandamento'), 'em andamento')]"),
        (By.XPATH, "//*[self::a or self::button or self::span][contains(translate(normalize-space(.), 'EMANDAMENTO', 'emandamento'), 'em andamento')]"),
    ]

    transacoes_element = None
    for by, selector in transacoes_selectors:
        try:
            transacoes_element = WebDriverWait(driver, 4).until(EC.presence_of_element_located((by, selector)))
            break
        except TimeoutException:
            continue

    if transacoes_element is not None:
        try:
            ActionChains(driver).move_to_element(transacoes_element).perform()
        except Exception:
            pass

    clicked_transacoes = _click_any(driver, transacoes_selectors, timeout=5)

    if not clicked_transacoes:
        for frame in driver.find_elements(By.CSS_SELECTOR, "iframe"):
            try:
                driver.switch_to.frame(frame)
                if _click_any(driver, transacoes_selectors, timeout=2):
                    clicked_transacoes = True
                    break
            except Exception:
                pass
            finally:
                driver.switch_to.default_content()

    if not clicked_transacoes:
        raise TimeoutException("No se encontró el menú 'Transações'")

    time.sleep(1)
    clicked_em_andamento = _click_any(driver, em_andamento_selectors, timeout=5)

    if not clicked_em_andamento:
        for frame in driver.find_elements(By.CSS_SELECTOR, "iframe"):
            try:
                driver.switch_to.frame(frame)
                if _click_any(driver, em_andamento_selectors, timeout=2):
                    clicked_em_andamento = True
                    break
            except Exception:
                pass
            finally:
                driver.switch_to.default_content()

    if not clicked_em_andamento:
        raise TimeoutException("No se encontró la opción 'Em Andamento'")

    WebDriverWait(driver, timeout).until(
        lambda d: "andamento" in d.current_url.lower() or d.execute_script("return document.readyState") == "complete"
    )


def go_to_cotacao_em_andamento(driver: webdriver.Chrome, timeout: int) -> None:
    cotacao_selectors = [
        (By.XPATH, "//a[contains(translate(normalize-space(.), 'COTAÇÃO', 'cotação'), 'cotação') or contains(translate(normalize-space(.), 'COTACAO', 'cotacao'), 'cotacao')]"),
        (By.XPATH, "//button[contains(translate(normalize-space(.), 'COTAÇÃO', 'cotação'), 'cotação') or contains(translate(normalize-space(.), 'COTACAO', 'cotacao'), 'cotacao')]"),
        (By.XPATH, "//*[self::a or self::button or self::span][contains(translate(normalize-space(.), 'COTACAOCOTAÇÃO', 'cotacaocotação'), 'cota')]"),
    ]

    em_andamento_selectors = [
        (By.XPATH, "//a[contains(translate(normalize-space(.), 'EMANDAMENTO', 'emandamento'), 'em andamento')]"),
        (By.XPATH, "//button[contains(translate(normalize-space(.), 'EMANDAMENTO', 'emandamento'), 'em andamento')]"),
        (By.XPATH, "//*[self::a or self::button or self::span][contains(translate(normalize-space(.), 'EMANDAMENTO', 'emandamento'), 'em andamento')]"),
    ]

    cotacao_element = None
    for by, selector in cotacao_selectors:
        try:
            cotacao_element = WebDriverWait(driver, 4).until(EC.presence_of_element_located((by, selector)))
            break
        except TimeoutException:
            continue

    if cotacao_element is not None:
        try:
            ActionChains(driver).move_to_element(cotacao_element).perform()
        except Exception:
            pass

    if not _click_any_with_frames(driver, cotacao_selectors, timeout_main=5, timeout_frame=2):
        raise TimeoutException("No se encontró el menú 'Cotação'")

    time.sleep(1)

    if not _click_any_with_frames(driver, em_andamento_selectors, timeout_main=5, timeout_frame=2):
        raise TimeoutException("No se encontró la opción 'Em Andamento' de Cotação")

    grid_selectors = [
        (By.CSS_SELECTOR, "table tbody tr"),
        (By.CSS_SELECTOR, ".k-grid-content table tbody tr"),
        (By.CSS_SELECTOR, ".ag-center-cols-container .ag-row"),
        (By.XPATH, "//*[contains(@class, 'grid') and .//*[self::tr or contains(@class,'row')]]"),
    ]

    grid_loaded = False
    for by, selector in grid_selectors:
        try:
            WebDriverWait(driver, timeout).until(lambda d: len(d.find_elements(by, selector)) > 0)
            grid_loaded = True
            break
        except TimeoutException:
            continue

    if not grid_loaded:
        WebDriverWait(driver, timeout).until(lambda d: d.execute_script("return document.readyState") == "complete")


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).strip().lower()


def _extract_first_table(driver: webdriver.Chrome) -> tuple[list[str], list[list[dict[str, str]]]]:
    script = """
const table = document.querySelector('table');
if (!table) return {headers: [], rows: []};
const headers = Array.from(table.querySelectorAll('thead th')).map(h => (h.innerText || '').trim());
const rows = Array.from(table.querySelectorAll('tbody tr')).map(tr =>
  Array.from(tr.querySelectorAll('td')).map(td => {
    const a = td.querySelector('a[href]');
    return {
      text: (td.innerText || '').trim(),
      link: a ? a.href : ''
    };
  })
);
return {headers, rows};
"""
    data = driver.execute_script(script)
    headers = data.get("headers", []) if isinstance(data, dict) else []
    rows = data.get("rows", []) if isinstance(data, dict) else []
    return headers, rows


def _extract_detail_tables(driver: webdriver.Chrome) -> list[dict]:
    script = """
const tables = Array.from(document.querySelectorAll('table'));
const headingFor = (table) => {
  let node = table;
  while (node) {
    let prev = node.previousElementSibling;
    while (prev) {
      const txt = (prev.innerText || '').trim();
      if (txt && txt.length < 120) return txt;
      prev = prev.previousElementSibling;
    }
    node = node.parentElement;
  }
  return '';
};
return tables.map(t => ({
  title: headingFor(t),
  headers: Array.from(t.querySelectorAll('thead th')).map(h => (h.innerText || '').trim()),
  rows: Array.from(t.querySelectorAll('tbody tr')).map(tr =>
    Array.from(tr.querySelectorAll('td')).map(td => (td.innerText || '').trim())
  )
}));
"""
    data = driver.execute_script(script)
    return data if isinstance(data, list) else []


def _extract_modal_tables(driver: webdriver.Chrome) -> list[dict]:
    script = """
const modal = document.querySelector('.modal.show, .modal.in, [role="dialog"], .k-window-content, .ui-dialog-content') || document.body;
const tables = Array.from(modal.querySelectorAll('table'));
const headingFor = (table) => {
  let node = table;
  while (node) {
    let prev = node.previousElementSibling;
    while (prev) {
      const txt = (prev.innerText || '').trim();
      if (txt && txt.length < 120) return txt;
      prev = prev.previousElementSibling;
    }
    node = node.parentElement;
  }
  return '';
};
return tables.map(t => ({
  title: headingFor(t),
  headers: Array.from(t.querySelectorAll('thead th')).map(h => (h.innerText || '').trim()),
  rows: Array.from(t.querySelectorAll('tbody tr')).map(tr =>
    Array.from(tr.querySelectorAll('td')).map(td => (td.innerText || '').trim())
  )
}));
"""
    data = driver.execute_script(script)
    return data if isinstance(data, list) else []


def _close_open_modal(driver: webdriver.Chrome, timeout: int) -> None:
    close_selectors = [
        (By.CSS_SELECTOR, ".modal.show button.close, .modal.in button.close, [role='dialog'] button.close"),
        (By.CSS_SELECTOR, ".modal.show [data-dismiss='modal'], .modal.in [data-dismiss='modal']"),
        (By.XPATH, "//button[contains(., 'Fechar') or contains(., 'Cerrar') or contains(., 'Close')]"),
        (By.XPATH, "//*[normalize-space(text())='×']"),
    ]
    _click_any_with_frames(driver, close_selectors, timeout_main=2, timeout_frame=1)
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: len(d.find_elements(By.CSS_SELECTOR, ".modal.show, .modal.in, [role='dialog']")) == 0
        )
    except TimeoutException:
        pass


def _extract_modal_items_and_campos(driver: webdriver.Chrome) -> list[dict]:
    script = """
const modal = document.querySelector('.modal.show, .modal.in, [role="dialog"], .k-window-content, .ui-dialog-content') || document.body;
const itemRows = Array.from(modal.querySelectorAll("span[id^='spanItem_']"));

const findText = (root, selectors) => {
  for (const sel of selectors) {
    const el = root.querySelector(sel);
    if (el) {
      const txt = (el.innerText || '').trim();
      if (txt) return txt;
    }
  }
  return '';
};

const itemData = itemRows.map((itemSpan) => {
  const suffix = itemSpan.id.replace('spanItem_', '');
  const container = itemSpan.closest('tr');
  const block = container ? container.parentElement : modal;

  const numero = (itemSpan.innerText || '').trim();
  const descricao = findText(block, [
    `#spanContratoID${suffix}`,
    `#spanDescContratoID${suffix}`,
    `#span1ContratoID${suffix}`,
  ]);

  const quantidade = findText(block, [
    `#quantidade${suffix}`,
    `input[name='quantidade${suffix}']`,
  ]);

  const unidade = findText(block, [
    `#UnidadeResp${suffix} option:checked`,
    `select[name='UnidadeResp${suffix}'] option:checked`,
  ]);

  const fabricante = findText(block, [
    `#fabricante${suffix}`,
    `input[name='Fabricante${suffix}']`,
  ]);

  const observacao = findText(block, [
    `input[name='Observacao${suffix}']`,
  ]);

  let camposAdicionais = '';
  const allRows = Array.from(block.querySelectorAll('tr'));
  const idx = allRows.findIndex(r => r.contains(itemSpan));
  if (idx >= 0) {
    for (let i = idx; i < Math.min(allRows.length, idx + 40); i++) {
      const txt = (allRows[i].innerText || '').trim();
      if (/campos adicionais/i.test(txt)) {
        camposAdicionais = txt;
        break;
      }
    }
  }

  return {
    item_numero: numero,
    item_descricao: descricao,
    quantidade,
    unidade,
    fabricante_marca: fabricante,
    observacao,
    campos_adicionais_texto: camposAdicionais,
  };
});

return itemData;
"""
    data = driver.execute_script(script)
    return data if isinstance(data, list) else []


def _extract_modal_items_and_campos_with_frames(driver: webdriver.Chrome) -> list[dict]:
    items = _extract_modal_items_and_campos(driver)
    if items:
        return items

    for frame in driver.find_elements(By.CSS_SELECTOR, "iframe"):
        try:
            driver.switch_to.frame(frame)
            items = _extract_modal_items_and_campos(driver)
            if items:
                return items
        except Exception:
            pass
        finally:
            driver.switch_to.default_content()

    return []


def _extract_modal_tables_with_frames(driver: webdriver.Chrome) -> list[dict]:
    tables = _extract_modal_tables(driver)
    if tables:
        return tables

    for frame in driver.find_elements(By.CSS_SELECTOR, "iframe"):
        try:
            driver.switch_to.frame(frame)
            tables = _extract_modal_tables(driver)
            if tables:
                return tables
        except Exception:
            pass
        finally:
            driver.switch_to.default_content()

    return []


def _go_to_next_grid_page(driver: webdriver.Chrome, timeout: int) -> bool:
    current_page = driver.execute_script(
        """
const active = document.querySelector('.k-pager-nav .k-state-selected, .pagination .active, .k-pager-wrap .k-link.k-state-selected');
return active ? (active.textContent || '').trim() : '';
"""
    )

    next_selectors = [
        (By.CSS_SELECTOR, ".k-pager-nav .k-i-arrow-e, .k-pager-nav .k-pager-nav.k-pager-next"),
        (By.CSS_SELECTOR, ".k-pager-wrap .k-pager-nav.k-pager-next"),
        (By.XPATH, "//a[contains(@class,'k-pager-next') and not(contains(@class,'k-state-disabled'))]"),
        (By.XPATH, "//button[contains(., 'Próxima') or contains(., 'Next')]"),
    ]

    for by, selector in next_selectors:
        candidates = driver.find_elements(by, selector)
        for element in candidates:
            classes = (element.get_attribute('class') or '').lower()
            disabled_attr = (element.get_attribute('disabled') or '').lower()
            if 'disabled' in classes or disabled_attr in {'true', 'disabled'}:
                continue
            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
                element.click()
            except Exception:
                try:
                    driver.execute_script("arguments[0].click();", element)
                except Exception:
                    continue

            try:
                WebDriverWait(driver, timeout).until(
                    lambda d: d.execute_script(
                        """
const active = document.querySelector('.k-pager-nav .k-state-selected, .pagination .active, .k-pager-wrap .k-link.k-state-selected');
return active ? (active.textContent || '').trim() : '';
"""
                    )
                    != current_page
                )
            except TimeoutException:
                continue

            WebDriverWait(driver, timeout).until(lambda d: d.execute_script("return document.readyState") == "complete")
            return True

    return False


def process_cotacoes_and_items(driver: webdriver.Chrome, timeout: int) -> None:
    grid_row_selectors = [
        (By.CSS_SELECTOR, "table tbody tr"),
        (By.CSS_SELECTOR, ".k-grid-content table tbody tr"),
        (By.CSS_SELECTOR, ".ag-center-cols-container .ag-row"),
    ]

    for by, selector in grid_row_selectors:
        try:
            WebDriverWait(driver, timeout).until(lambda d: len(d.find_elements(by, selector)) > 0)
            break
        except TimeoutException:
            continue

    page_number = 1
    total_printed = 0
    cotacoes_json: list[dict] = []

    while True:
        list_url = driver.current_url
        headers, rows = _extract_first_table(driver)
        if not headers or not rows:
            print("⚠️ No se detectó una grilla de cotaciones con datos para recorrer.")
            return

        normalized_headers = [_normalize_text(h) for h in headers]
        id_col_index = -1
        for i, h in enumerate(normalized_headers):
            if "id cotacao me" in h or "id cotacao" in h:
                id_col_index = i
                break

        if id_col_index < 0:
            print("⚠️ No se encontró la columna 'ID Cotação ME'.")
            return

        print(f"\n📄 Página {page_number} | filas detectadas: {len(rows)}")

        for row_index, row_cells in enumerate(rows, start=1):
            if driver.current_url != list_url:
                driver.get(list_url)
                WebDriverWait(driver, timeout).until(lambda d: d.execute_script("return document.readyState") == "complete")
                time.sleep(1)

            row_data = {}
            for idx, header in enumerate(headers):
                value = row_cells[idx].get("text", "") if idx < len(row_cells) else ""
                row_data[header] = value

            id_value = row_cells[id_col_index].get("text", "") if id_col_index < len(row_cells) else ""
            id_link = row_cells[id_col_index].get("link", "") if id_col_index < len(row_cells) else ""
            total_printed += 1

            print(f"\n===== COTACIÓN {total_printed} | PÁGINA {page_number} FILA {row_index} | ID Cotação ME: {id_value} =====")
            print(f"Link ID Cotação ME: {id_link}")
            for k, v in row_data.items():
                print(f"{k}: {v}")

            cotacao_entry = {
                "pagina": page_number,
                "fila": row_index,
                "id_cotacao_me": id_value,
                "id_cotacao_link": id_link,
                "campos": row_data,
                "itens_campos_adicionais": [],
            }

            clicked_detail = False
            id_click_xpath = f"(//table//tbody/tr)[{row_index}]/td[{id_col_index + 1}]//*[self::a or self::button]"
            id_text_xpath = f"//table//tbody/tr/td[{id_col_index + 1}]//*[self::a or self::button][contains(normalize-space(.), '{id_value}')]"
            try:
                link_elem = None
                try:
                    link_elem = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((By.XPATH, id_text_xpath)))
                except Exception:
                    link_elem = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((By.XPATH, id_click_xpath)))
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", link_elem)
                link_elem.click()
                clicked_detail = True
            except Exception:
                if id_link:
                    try:
                        driver.get(id_link)
                        clicked_detail = True
                    except Exception:
                        clicked_detail = False

            if not clicked_detail:
                print("⚠️ No se pudo abrir detalle para esta cotización.")
                cotacoes_json.append(cotacao_entry)
                continue

            try:
                WebDriverWait(driver, timeout).until(lambda d: d.execute_script("return document.readyState") == "complete")
                time.sleep(1)

                modal_items = _extract_modal_items_and_campos_with_frames(driver)
                modal_tables = _extract_modal_tables_with_frames(driver)
                matching = []
                for t in modal_tables:
                    ttitle = _normalize_text(t.get("title", ""))
                    if "item" in ttitle or "campo adicional" in ttitle or "campos adicionais" in ttitle:
                        matching.append(t)

                if not matching:
                    matching = [t for t in modal_tables if t.get("rows")][:4]

                print("--- DETALLE MODAL: ITENS / CAMPOS ADICIONAIS ---")
                details_json = []

                if modal_items:
                    print(f"Itens detectados en modal: {len(modal_items)}")
                    details_json.append({
                        "seccion": "Itens (blocos do modal)",
                        "headers": [],
                        "registros": modal_items,
                    })
                    for item_idx, item_data in enumerate(modal_items, start=1):
                        print(f"  Item {item_idx}: {item_data}")

                if not matching and not modal_items:
                    print("⚠️ No se encontraron tablas de detalle en el modal.")

                for t_idx, table in enumerate(matching, start=1):
                    title = table.get("title", "").strip() or f"Tabla {t_idx}"
                    theaders = table.get("headers", [])
                    trows = table.get("rows", [])
                    print(f"Sección: {title}")

                    rows_json = []
                    for r_idx, r in enumerate(trows, start=1):
                        mapped = {}
                        for c_idx in range(max(len(theaders), len(r))):
                            key = theaders[c_idx] if c_idx < len(theaders) and theaders[c_idx] else f"col_{c_idx + 1}"
                            mapped[key] = r[c_idx] if c_idx < len(r) else ""
                        print(f"  Registro {r_idx}: {mapped}")
                        rows_json.append(mapped)

                    details_json.append({
                        "seccion": title,
                        "headers": theaders,
                        "registros": rows_json,
                    })

                cotacao_entry["itens_campos_adicionais"] = details_json

            except Exception as exc:
                print(f"⚠️ Error extrayendo detalle de la cotización {id_value}: {exc}")
            finally:
                _close_open_modal(driver, timeout=3)
                if driver.current_url != list_url:
                    driver.get(list_url)
                    WebDriverWait(driver, timeout).until(lambda d: d.execute_script("return document.readyState") == "complete")
                time.sleep(1)

            cotacoes_json.append(cotacao_entry)

        if not _go_to_next_grid_page(driver, timeout=4):
            break

        page_number += 1
        time.sleep(1)

    print(f"\n✅ Total de cotizaciones impresas: {total_printed}")
    print("\n===== JSON COMPLETO DE COTIZACIONES =====")
    print(json.dumps(cotacoes_json, ensure_ascii=False, indent=2))




def _run_step(step_name: str, action) -> None:
    print(f"➡️ {step_name}")
    try:
        action()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Fallo en paso '{step_name}': {exc!r}") from exc

def main() -> int:
    parser = argparse.ArgumentParser(description="RPA login para me.com.br")
    parser.add_argument("--login", default=os.getenv("ME_LOGIN", DEFAULT_LOGIN), help="Login de acceso")
    parser.add_argument("--password", default=os.getenv("ME_PASSWORD", DEFAULT_PASSWORD), help="Senha de acceso")
    parser.add_argument("--headed", action="store_true", help="Ejecuta con navegador visible")
    parser.add_argument("--timeout", type=int, default=25, help="Timeout general en segundos")
    parser.add_argument("--debug-traceback", action="store_true", help="Imprime traceback completo al fallar")
    args = parser.parse_args()

    driver: Optional[webdriver.Chrome] = None

    try:
        driver = build_driver(headless=not args.headed)
        _run_step("Abrir página de login", lambda: open_login_page(driver, args.timeout))
        _run_step("Realizar login", lambda: do_login(driver, args.login, args.password))
        _run_step("Validar login", lambda: validate_login(driver, args.timeout))
        _run_step("Resolver pantalla timezone", lambda: handle_timezone_screen(driver, args.timeout))
        _run_step("Resolver ventana de confirmación", lambda: handle_confirmation_window(driver, args.timeout))
        _run_step("Continuar navegación en comunicado", lambda: handle_continue_navigation(driver, args.timeout))
        _run_step("Ir a Transações > Em Andamento", lambda: go_to_transacoes_em_andamento(driver, args.timeout))
        _run_step("Ir a Cotação > Em Andamento", lambda: go_to_cotacao_em_andamento(driver, args.timeout))
        _run_step("Procesar cotizaciones e ítems", lambda: process_cotacoes_and_items(driver, args.timeout))
        print(f"✅ Login exitoso. URL final: {driver.current_url}")
        return 0
    except SessionNotCreatedException as exc:
        print("❌ Error creando sesión de ChromeDriver.")
        print("   Revisa compatibilidad entre Chrome/Chromium y ChromeDriver.")
        print("   En Linux headless instala librerías de sistema requeridas y prueba con --headed para diagnóstico.")
        print("   Puedes exportar CHROMEDRIVER_LOG=/tmp/chromedriver.log y CHROMEDRIVER_VERBOSE=1 para más detalle.")
        print(f"   Detalle: {exc!r}")
        if args.debug_traceback:
            traceback.print_exc()
        return 1
    except WebDriverException as exc:
        print(f"❌ Error de WebDriver: {exc!r}")
        if args.debug_traceback:
            traceback.print_exc()
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"❌ Error en el flujo RPA: {exc!r}")
        if args.debug_traceback:
            traceback.print_exc()
        return 1
    finally:
        if driver is not None:
            driver.quit()


if __name__ == "__main__":
    sys.exit(main())
