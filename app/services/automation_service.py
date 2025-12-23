import logging
import threading
from typing import List, Optional, Union
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoAlertPresentException, WebDriverException, InvalidSessionIdException

# Import your schemas here
from app.schemas.service import AirtimeRequest, DataRequest, ElectricityRequest, TVRequest, TVRefreshRequest
from app.core.config import settings

logger = logging.getLogger(__name__)

class VTUAutomator:
    _instance = None
    _driver = None
    _wait = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(VTUAutomator, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        # Initialize driver only if it doesn't exist or is closed
        if not self._driver:
            with self._lock:
                if not self._driver:
                    self.setup_driver()

    def setup_driver(self):
        """Initializes High-Performance Headless Chrome."""
        chrome_options = Options()

        # --- SPEED HACK 1: Eager Loading ---
        # Don't wait for the spinning wheel to stop. Interact as soon as DOM is ready.
        chrome_options.page_load_strategy = 'eager'

        # --- SPEED HACK 2: Block Images & Heavy Assets ---
        # 2 = Block, 1 = Allow
        prefs = {
            "profile.managed_default_content_settings.images": 1, # Changed to 1 (Allow) to fix visibility issues
            "profile.default_content_setting_values.notifications": 2,
            "profile.managed_default_content_settings.stylesheets": 1, # Changed to 1 (Allow) - Layout needed for Selenium visibility
            "profile.managed_default_content_settings.cookies": 1, # Changed to 1 (Allow) - Some sites need cookies
            "profile.managed_default_content_settings.javascript": 1, # Keep JS ON
            "profile.managed_default_content_settings.plugins": 2,
            "profile.managed_default_content_settings.popups": 2,
            "profile.managed_default_content_settings.geolocation": 2,
            "profile.managed_default_content_settings.media_stream": 2,
        }
        chrome_options.add_experimental_option("prefs", prefs)

        # --- STANDARD FLAGS ---
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")

        # --- NETWORK OPTIMIZATIONS ---
        chrome_options.add_argument("--dns-prefetch-disable") # Disable DNS prefetching
        chrome_options.add_argument("--disable-extensions") # Disable extensions
        chrome_options.add_argument("--renderer-process-limit=2") # Limit renderer processes
        chrome_options.add_argument("--disable-dev-shm-usage")

        # --- ANTI-DETECTION ---
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        chrome_options.add_argument(f"user-agent={user_agent}")

        try:
            VTUAutomator._driver = webdriver.Chrome(
                service=ChromeService(ChromeDriverManager().install()),
                options=chrome_options
            )
            VTUAutomator._driver.maximize_window()
            VTUAutomator._wait = WebDriverWait(VTUAutomator._driver, 10) # Keep explicit wait short
            logger.info("High-Performance WebDriver initialized (Singleton).")
        except Exception as e:
            logger.error(f"Failed to initialize WebDriver: {e}")
            raise e

    @property
    def driver(self):
        return VTUAutomator._driver

    @property
    def wait(self):
        return VTUAutomator._wait

    def _safe_click(self, element):
        """
        Forces a click on an element using JavaScript.
        Fixes 'ElementClickInterceptedException' in headless mode.
        """
        try:
            # 1. Scroll element to center to avoid sticky headers/footers
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            # 2. Try normal click
            element.click()
        except Exception:
            # 3. If blocked, force click via JS
            logger.info("Normal click failed. Forcing JS Click...")
            self.driver.execute_script("arguments[0].click();", element)

    def _switch_to_iframe_with_element(self, locator_tuple) -> bool:
        """
        Helper: Rapidly scans all iframes to find one containing a specific element.
        """
        self.driver.switch_to.default_content()
        try:
            iframes = self.wait.until(EC.presence_of_all_elements_located((By.TAG_NAME, "iframe")))
            for frame in iframes:
                self.driver.switch_to.frame(frame)
                if len(self.driver.find_elements(*locator_tuple)) > 0:
                    return True
                self.driver.switch_to.default_content()
        except TimeoutException:
            pass
        return False

    def _sltv_login_and_navigate(self, username, password):
        """Helper: Handles Login and Navigation to Recharge Page"""
        logger.info("Navigating to SLTV Login...")
        self.driver.get("https://sltvpro.com/main/lco_login")

        # Fast Login
        self.wait.until(EC.visibility_of_element_located((By.ID, 'name'))).send_keys(username)
        self.driver.find_element(By.ID, 'password').send_keys(password)

        # Use safe_click for login button too, just in case
        login_btn = self.driver.find_element(By.XPATH, "//*[@id='loginForm']/button")
        self._safe_click(login_btn)

        logger.info("Login successful. Navigating to Recharge page...")
        recharge_link = self.wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "RECHARGE")))
        self._safe_click(recharge_link)

    def get_sltv_user_details(self, request: TVRequest) -> Union[dict, bool]:
        """
        Logs in, searches for Smart Card, scrapes 5 detail lines, and returns them.
        Thread-safe and Auto-Recovering.
        """
        with self._lock:
            for attempt in range(2): # Retry once
                try:
                    if not self.driver:
                        self.setup_driver()

                    # Ensure clean session
                    try:
                        self.driver.delete_all_cookies()
                    except Exception:
                        pass

                    self._sltv_login_and_navigate(settings.SLTV_USERNAME, settings.SLTV_PASSWORD)

                    logger.info(f"Searching for IUC: {request.smart_card_number}")
                    if self._switch_to_iframe_with_element((By.ID, "keywordSearch")):
                        input_element = self.driver.find_element(By.ID, "keywordSearch")

                        # JS Inject
                        self.driver.execute_script(f"arguments[0].value = '{request.smart_card_number}';", input_element)
                        self.driver.execute_script("arguments[0].dispatchEvent(new Event('input'));", input_element)
                        self.driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", input_element)

                        self.driver.find_element(By.NAME, "customerSearch").click()

                        # Scrape the 5 Divs
                        # Scrape the 5 Divs
                        logger.info("Extracting user details...")
                        user_details = {}

                        for i in range(1, 6):
                            xpath = f"/html/body/div[5]/div[2]/div/div[2]/div[{i}]"
                            try:
                                if i == 1:
                                    element = self.wait.until(EC.visibility_of_element_located((By.XPATH, xpath)))
                                else:
                                    element = self.driver.find_element(By.XPATH, xpath)

                                text = element.text.strip()
                                # Parse "Key:\nValue" format
                                if ":" in text:
                                    parts = text.split(":", 1)
                                    raw_key = parts[0].strip()
                                    value = parts[1].strip() if len(parts) > 1 else ""

                                    # Normalize key
                                    key = raw_key.lower().replace(" ", "_").replace(".", "")
                                    user_details[key] = value
                                    logger.info(f"Detail [{key}]: {value}")
                                else:
                                    # Fallback for unexpected format
                                    user_details[f"detail_{i}"] = text
                                    logger.info(f"Detail [{i}]: {text}")

                            except Exception:
                                logger.warning(f"Could not scrape detail #{i}")

                        self.driver.switch_to.default_content()
                        return user_details
                    else:
                        logger.error("Could not find Search Iframe.")
                        return False

                except (InvalidSessionIdException, WebDriverException) as e:
                    logger.warning(f"Driver crashed or invalid session (Attempt {attempt+1}/2): {e}")
                    # Force reset
                    VTUAutomator._driver = None
                    VTUAutomator._instance = None # Optional, but safer to fully reset if needed
                    # Loop will retry setup_driver()
                except Exception as e:
                    logger.error(f"Get User Details failed: {e}")
                    return False
            return False

    def purchase_tv(self, request: TVRequest) -> Union[str, bool]:
        """
        Full Flow: Login -> Search -> Select Plan -> Recharge -> Confirm -> Capture Success.
        Thread-safe and Auto-Recovering.
        """
        with self._lock:
            for attempt in range(2):
                try:
                    if not self.driver:
                        self.setup_driver()

                    try:
                        self.driver.delete_all_cookies()
                    except Exception:
                        pass

                    self._sltv_login_and_navigate(settings.SLTV_USERNAME, settings.SLTV_PASSWORD)

                    logger.info(f"Processing Purchase for: {request.smart_card_number}")
                    if self._switch_to_iframe_with_element((By.ID, "keywordSearch")):
                        input_element = self.driver.find_element(By.ID, "keywordSearch")

                        self.driver.execute_script(f"arguments[0].value = '{request.smart_card_number}';", input_element)
                        self.driver.execute_script("arguments[0].dispatchEvent(new Event('input'));", input_element)
                        self.driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", input_element)

                        self.driver.find_element(By.NAME, "customerSearch").click()

                        result_link = self.wait.until(EC.element_to_be_clickable(
                            (By.XPATH, "/html/body/div[5]/div[2]/div/table/tbody/tr/td[6]/a")
                        ))
                        self._safe_click(result_link)
                        self.driver.switch_to.default_content()
                    else:
                        raise Exception("Search iframe not found.")

                    logger.info("Selecting Plan...")
                    if request.value == 1:
                        plan_xpath = "//*[@id='rechagestblist']/table/tbody/tr[1]/td[2]/input"
                    else:
                        plan_xpath = "//*[@id='rechagestblist']/table/tbody/tr[2]/td[2]/input"
                        
                    recharge_btn_xpath = "//*[@id='recharge']"
                    success_msg_xpath = "//*[@id='error']/div"

                    if self._switch_to_iframe_with_element((By.XPATH, plan_xpath)):
                        # --- A. Click Plan (Safe Click) ---
                        plan_element = self.wait.until(EC.presence_of_element_located((By.XPATH, plan_xpath)))
                        self._safe_click(plan_element)

                        # --- B. Click Recharge (Safe Click) ---
                        recharge_btn = self.wait.until(EC.presence_of_element_located((By.XPATH, recharge_btn_xpath)))
                        self._safe_click(recharge_btn)

                        # --- C. Handle Popup ---
                        try:
                            self.wait.until(EC.alert_is_present())
                            # CHANGED TO ACCEPT: 'dismiss' usually cancels the transaction. 'accept' hits OK.
                            self.driver.switch_to.alert.accept()
                            logger.info("Popup Accepted.")
                        except TimeoutException:
                            logger.warning("No popup appeared.")

                        # --- D. Capture Success Message ---
                        logger.info("Waiting for success message...")
                        final_message = "Success (Message not captured)"

                        try:
                            # Check immediately
                            msg_element = self.wait.until(EC.visibility_of_element_located((By.XPATH, success_msg_xpath)))
                            final_message = msg_element.text
                        except TimeoutException:
                            logger.info("Page reloaded, hunting for message...")
                            if self._switch_to_iframe_with_element((By.XPATH, success_msg_xpath)):
                                 msg_element = self.wait.until(EC.visibility_of_element_located((By.XPATH, success_msg_xpath)))
                                 final_message = msg_element.text

                        logger.info(f"TRANSACTION COMPLETE: {final_message}")
                        self.driver.switch_to.default_content()

                        print(final_message)
                        return final_message

                    else:
                        raise Exception("Plan Selection iframe not found.")

                except (InvalidSessionIdException, WebDriverException) as e:
                    logger.warning(f"Driver crashed or invalid session (Attempt {attempt+1}/2): {e}")
                    VTUAutomator._driver = None
                    VTUAutomator._instance = None
                except Exception as e:
                    logger.error(f"TV purchase failed: {e}")
                    return False
            return False


    def refresh_tv(self, request: TVRefreshRequest) -> Union[str, bool]:
        """
        Full Flow: Login -> Search -> Click Refresh -> Capture Success.
        Thread-safe and Auto-Recovering.
        """
        with self._lock:
            for attempt in range(2):
                try:
                    if not self.driver:
                        self.setup_driver()

                    try:
                        self.driver.delete_all_cookies()
                    except Exception:
                        pass

                    self._sltv_login_and_navigate(settings.SLTV_USERNAME, settings.SLTV_PASSWORD)

                    logger.info(f"Processing Purchase for: {request.smart_card_number}")
                    if self._switch_to_iframe_with_element((By.ID, "keywordSearch")):
                        input_element = self.driver.find_element(By.ID, "keywordSearch")

                        self.driver.execute_script(f"arguments[0].value = '{request.smart_card_number}';", input_element)
                        self.driver.execute_script("arguments[0].dispatchEvent(new Event('input'));", input_element)
                        self.driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", input_element)

                        self.driver.find_element(By.NAME, "customerSearch").click()

                        result_link = self.wait.until(EC.element_to_be_clickable(
                            (By.XPATH, "/html/body/div[5]/div[2]/div/table/tbody/tr/td[7]/a")
                        ))
                        self._safe_click(result_link)
                        self.driver.switch_to.default_content()

                        # Capture Success Message
                        success_msg_xpath = "/html/body/div[1]/div"

                        # Check if we need to switch to an iframe to see the message
                        if self._switch_to_iframe_with_element((By.XPATH, success_msg_xpath)):
                            try:
                                msg_element = self.wait.until(EC.visibility_of_element_located((By.XPATH, success_msg_xpath)))
                                final_message = msg_element.text
                                logger.info(f"REFRESH COMPLETE: {final_message}")
                                self.driver.switch_to.default_content()
                                return final_message
                            except TimeoutException:
                                logger.warning("Refresh success message element found but timed out.")
                                self.driver.switch_to.default_content()
                                return "Refresh initiated (Message not captured)"
                        else:
                            # Fallback: check default content if not found in any iframe
                            try:
                                msg_element = self.wait.until(EC.visibility_of_element_located((By.XPATH, success_msg_xpath)))
                                final_message = msg_element.text
                                logger.info(f"REFRESH COMPLETE (Default Content): {final_message}")
                                return final_message
                            except TimeoutException:
                                logger.warning("Refresh success message not found in iframes or default content.")
                                return "Refresh initiated (Message not captured)"
                    else:
                        raise Exception("Search iframe not found.")


                except (InvalidSessionIdException, WebDriverException) as e:
                    logger.warning(f"Driver crashed or invalid session (Attempt {attempt+1}/2): {e}")
                    VTUAutomator._driver = None
                    VTUAutomator._instance = None
                except Exception as e:
                    logger.error(f"TV purchase failed: {e}")
                    return False
            return False

    def close(self):
        """
        Closes the driver. Should be called only when shutting down the app or resetting.
        """
        if VTUAutomator._driver:
            try:
                VTUAutomator._driver.quit()
            except Exception:
                pass
            VTUAutomator._driver = None
            VTUAutomator._wait = None
