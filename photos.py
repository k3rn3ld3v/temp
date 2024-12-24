from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from bs4 import BeautifulSoup
import time
import os
import requests
import logging
import uuid
import sys
from concurrent.futures import ThreadPoolExecutor

firefox_service = Service('./geckodriver.exe')

logging.basicConfig(level=logging.INFO)

class FacebookImageDownloader:
    def __init__(self, username):
        self.username = username
        self.user_id = self.get_facebook_user_id()
        if not self.user_id:
            logging.error("Failed to retrieve user ID.")
            sys.exit(1)
        self.folder_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "photos", self.user_id)
        os.makedirs(self.folder_path, exist_ok=True)
        options = Options()
        options.add_argument('--headless')
        self.driver = webdriver.Firefox(service=firefox_service, options=options)

    def get_facebook_user_id(self):
        try:
            url = f"https://www.facebook.com/{self.username}"
            html = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}).text
            soup = BeautifulSoup(html, "html.parser")
            meta = soup.find("meta", {"property": "al:ios:url"})
            return meta["content"].split("/")[-1] if meta else None
        except requests.RequestException as e:
            logging.error(f"Network error occurred: {e}")
            return None

    def generate_filename(self):
        return f"{uuid.uuid4()}.jpg"

    def download_image(self, image_url):
        try:
            filename = os.path.join(self.folder_path, self.generate_filename())
            response = requests.get(image_url, stream=True)
            if response.status_code == 200:
                with open(filename, 'wb') as file:
                    for chunk in response.iter_content(1024):
                        file.write(chunk)
                logging.info(f"Image saved as {filename}.")
            else:
                logging.warning(f"Failed to download image from {image_url}.")
        except requests.RequestException as e:
            logging.error(f"Error downloading image: {e}")

    def run(self):
        try:
            with self.driver as driver:
                driver.get(f"https://www.facebook.com/{self.username}/photos/")
                time.sleep(5)

                divs_with_close = driver.find_elements(By.XPATH, "//div[@aria-label='Close']")
                for div in divs_with_close:
                    driver.execute_script("arguments[0].scrollIntoView(true);", div)
                    div.click()
                    time.sleep(1)
                    last_height = driver.execute_script("return document.body.scrollHeight")
                    while True:
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(2)
                        new_height = driver.execute_script("return document.body.scrollHeight")
                        if new_height == last_height:
                            logging.info("No more images to load")
                            break
                        last_height = new_height

                a_tags = driver.find_elements(By.TAG_NAME, "a")
                urls_to_process = []
                for tag in a_tags:
                    href = tag.get_attribute("href")
                    if href == f"https://www.facebook.com/{self.username}/photos" and "Photos" in tag.text:
                        first_parent = tag.find_element(By.XPATH, "..")
                        if first_parent.tag_name != "span":
                            continue
                        second_parent = first_parent.find_element(By.XPATH, "..")
                        if second_parent.tag_name != "h2":
                            continue
                        parent = tag
                        for i in range(7):
                            parent = parent.find_element(By.XPATH, "..")
                        parent_html = parent.get_attribute("outerHTML")
                        soup = BeautifulSoup(parent_html, "html.parser")
                        img_tags = soup.find_all("img")
                        for img_tag in img_tags:
                            parent = img_tag.find_parent()
                            if parent and parent.has_attr("href"):
                                urls_to_process.append(parent["href"])
                        break
                logging.info(f"Found {len(urls_to_process)} URLs to process")
                with ThreadPoolExecutor(max_workers=5) as executor:
                    for url in urls_to_process:
                        driver.get(url)
                        time.sleep(5)
                        img_elements = driver.find_elements(By.TAG_NAME, "img")
                        if img_elements:
                            img = img_elements[0]
                            src = img.get_attribute("src")
                            if src and "fbcdn.net" in src:
                                executor.submit(self.download_image, src)
                        time.sleep(1)  # Rate limiting
        except Exception as e:
            logging.error(f"An error occurred: {e}")
        finally:
            self.driver.quit()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        logging.error("Please provide a Facebook username as an argument.")
        sys.exit(1)
    username = sys.argv[1]
    downloader = FacebookImageDownloader(username)
    downloader.run()