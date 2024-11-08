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
    def __init__(self, base_urls, max_workers=10, max_concurrent_requests=20, sitemap_file='landui_sitemap.xml'):
        self.base_urls = base_urls
        self.domain = urlparse(base_urls[0]).netloc  # Using first URL for domain
        self.visited_urls = set()
        self.url_queue = Queue()
        self.url_lock = threading.Lock()
        self.sitemap_lock = threading.Lock()  # Add lock for sitemap operations
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.semaphore = BoundedSemaphore(max_concurrent_requests)
        self.sitemap_file = sitemap_file
        
        # Initialize sitemap file
        self._init_sitemap_file()
        
    def _init_sitemap_file(self):
        with open(self.sitemap_file, 'w', encoding='utf-8') as f:
            f.write('<?xml version="1.0" encoding="utf-8"?>\n')
            f.write('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')

    def append_to_sitemap(self, url):
        with self.sitemap_lock:
            with open(self.sitemap_file, 'a', encoding='utf-8') as f:
                f.write('    <url>\n')
                f.write(f'        <loc>{url}</loc>\n')
                f.write('        <lastmod>2012-12-01</lastmod>\n')
                f.write('        <changefreq>daily</changefreq>\n')
                f.write('        <priority>0.8</priority>\n')
                f.write('    </url>\n')

    def finalize_sitemap(self):
        with self.sitemap_lock:
            with open(self.sitemap_file, 'a', encoding='utf-8') as f:
                f.write('</urlset>')

    def is_valid_url(self, url):
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except ValueError:
            return False

    def is_under_root_urls(self, url):
        return any(url.startswith(root_url) for root_url in self.base_urls)
    
    def crawl_parallel(self):
        # Initialize queue with all base URLs
        for url in self.base_urls:
            self.url_queue.put(url)
        
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
                if url.lower().endswith(".html"):
                    self.visited_urls.add(url[:-5])

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
                print(f"Found URL: {url}", flush=True)
                
                # Append URL to sitemap immediately after successful crawl
                self.append_to_sitemap(url)

                for link in soup.find_all('a'):
                    href = link.get('href')
                    if href:
                        full_url = urljoin(url, href)
                        if urlparse(full_url).netloc == self.domain and self.is_under_root_urls(full_url):
                            self.url_queue.put(full_url)

            except Exception as e:
                print(f"Error crawling {url}: {str(e)}", file=sys.stderr)


def main():
    base_urls = [
        "https://www.landui.com/docs/",
        "https://www.landui.com/help/",
        "https://www.landui.com/help/ilist-0"
    ]
    
    print("Starting crawl for all base URLs")
    crawler = WebCrawler(base_urls)
    crawler.crawl_parallel()
    crawler.finalize_sitemap()  # Close the XML structure
    crawler.executor.shutdown()
    
    print("\nCrawling completed!")
    print(f"Total unique URLs found: {len(crawler.visited_urls)}")
    print(f"Sitemap has been generated: {crawler.sitemap_file}")

if __name__ == "__main__":
    main()
