#!/usr/bin/env python3

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import sys
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
import threading
from threading import BoundedSemaphore
from datetime import datetime
import xml.etree.ElementTree as ET
from xml.dom import minidom

class WebCrawler:
    root_urls = [
        "https://www.landui.com/docs/",
        "https://www.landui.com/help/",
        "https://www.landui.com/help/ilist-0"
    ]

    def __init__(self, base_url, max_workers=10, max_concurrent_requests=20):
        self.base_url = base_url
        self.domain = urlparse(base_url).netloc
        self.visited_urls = set()
        self.url_queue = Queue()
        self.url_lock = threading.Lock()
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.semaphore = BoundedSemaphore(max_concurrent_requests)
        
    def is_valid_url(self, url):
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except ValueError:
            return False

    def is_under_root_urls(self, url):
        return any(url.startswith(root_url) for root_url in self.root_urls)
    
    def crawl_parallel(self):
        self.url_queue.put(self.base_url)
        futures = []

        while True:
            try:
                url = self.url_queue.get(timeout=5)  # Wait for 5 seconds for new URLs
            except:
                # If no URLs in queue for 5 seconds, check if all tasks are done
                if all(future.done() for future in futures):
                    break
                continue

            with self.url_lock:
                if url in self.visited_urls:
                    self.url_queue.task_done()
                    continue
                self.visited_urls.add(url)

            future = self.executor.submit(self.process_url, url)
            futures.append(future)
            self.url_queue.task_done()

    def process_url(self, url):
        if not self.is_valid_url(url) or not self.is_under_root_urls(url):
            return

        with self.semaphore:
            try:
                response = requests.get(url, timeout=10)
                if response.status_code != 200:
                    return

                soup = BeautifulSoup(response.text, 'html.parser')
                print(f"Found URL: {url}")

                for link in soup.find_all('a'):
                    href = link.get('href')
                    if href:
                        full_url = urljoin(url, href)
                        if urlparse(full_url).netloc == self.domain and self.is_under_root_urls(full_url):
                            self.url_queue.put(full_url)

            except Exception as e:
                print(f"Error crawling {url}: {str(e)}", file=sys.stderr)

    @staticmethod
    def generate_sitemap(urls, output_file='sitemap.xml'):
        urlset = ET.Element('urlset')
        
        for url in sorted(urls):

            print(f"Adding URL to sitemap: {url}")

            url_element = ET.SubElement(urlset, 'url')
            
            # Add loc element
            loc = ET.SubElement(url_element, 'loc')
            loc.text = url
            
            # Add lastmod element
            lastmod = ET.SubElement(url_element, 'lastmod')
            lastmod.text = datetime.now().strftime('%Y-%m-%d')
            
            # Add changefreq element
            changefreq = ET.SubElement(url_element, 'changefreq')
            changefreq.text = 'daily'
            
            # Add priority element
            priority = ET.SubElement(url_element, 'priority')
            priority.text = '0.8'
        
        # Create pretty XML string
        xml_str = minidom.parseString(ET.tostring(urlset)).toprettyxml(indent="    ")
        
        # Write to file
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('<?xml version="1.0" encoding="utf-8"?>\n')
            # Remove the first line (XML declaration) since we already wrote it
            f.write('\n'.join(xml_str.split('\n')[1:]))

def main():
    all_visited_urls = set()
    for start_url in WebCrawler.root_urls:
        print(f"\nStarting crawl for: {start_url}")
        crawler = WebCrawler(start_url)
        crawler.crawl_parallel()
        crawler.executor.shutdown()
        all_visited_urls.update(url for url in crawler.visited_urls if crawler.is_under_root_urls(url))
    
    print("\nCrawling completed!")
    print(f"Total unique URLs found: {len(all_visited_urls)}")
    
    # Generate sitemap XML
    output_file = 'landui_sitemap.xml'
    WebCrawler.generate_sitemap(all_visited_urls, output_file)
    print(f"\nSitemap has been generated: {output_file}")

if __name__ == "__main__":
    main()
