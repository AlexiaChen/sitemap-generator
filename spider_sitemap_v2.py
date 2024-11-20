#!/usr/bin/env python3

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import sys
from concurrent.futures import ThreadPoolExecutor
from queue import Queue, Empty  # Fix: import Empty explicitly
import threading
from threading import BoundedSemaphore
from datetime import datetime
import xml.etree.ElementTree as ET
from xml.dom import minidom
import argparse
from urllib.parse import quote, urlparse, urlunparse

class WebCrawler:

    NAV_URLS = [
        "https://www.landui.com/",
        "https://www.landui.com/eve/activity",
        "https://www.landui.com/mart/",
        "https://www.landui.com/security/",
        "https://www.landui.com/customer/",
        "https://www.landui.com/cps/",
        "https://www.landui.com/docs/",
        "https://www.landui.com/help/aboutus.html",
    ]


    def __init__(self, base_urls, recursive=False, max_workers=10, max_concurrent_requests=20, sitemap_file='sitemap.xml'):
        self.base_urls = base_urls
        self.recursive = recursive
        self.domain = urlparse(base_urls[0]).netloc  # Using first URL for domain
        self.visited_urls = set()
        self.url_queue = Queue()
        self.url_lock = threading.Lock()
        self.sitemap_lock = threading.Lock()  # Add lock for sitemap operations
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.semaphore = BoundedSemaphore(max_concurrent_requests)
        self.sitemap_file = sitemap_file
        self.root_urls = set(base_urls)  # Store initial URLs
        
        # Initialize sitemap file
        self._init_sitemap_file()
        
    def _init_sitemap_file(self):
        with open(self.sitemap_file, 'w', encoding='utf-8') as f:
            f.write('<?xml version="1.0" encoding="utf-8"?>\n')
            f.write('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')

    def append_to_sitemap(self, url):
        # Encode Chinese characters in URL while preserving the URL structure
        encoded_url = quote(url, safe=':/?=&%')
        current_date = datetime.now().strftime('%Y-%m-%d')
        priority = '1' if url in self.NAV_URLS else '0.8'
        with self.sitemap_lock:
            with open(self.sitemap_file, 'a', encoding='utf-8') as f:
                f.write('    <url>\n')
                f.write(f'        <loc>{encoded_url}</loc>\n')
                f.write(f'        <lastmod>{current_date}</lastmod>\n')
                f.write('        <changefreq>daily</changefreq>\n')
                f.write(f'        <priority>{priority}</priority>\n')
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
    
    def is_valid_link_to_crawl(self, full_url):
        """验证链接是否需要爬取"""
        return (
            urlparse(full_url).netloc == self.domain
            and self.is_under_root_urls(full_url)
            and full_url not in self.visited_urls
        )

    def should_process_links(self, url):
        """判断是否需要处理页面中的链接"""
        return self.recursive or url in self.root_urls

    
    def process_found_link(self, full_url):
        """处理发现的新链接"""
        with self.url_lock:
            if full_url not in self.visited_urls:
                self.visited_urls.add(full_url)
                if self.recursive:
                    self.url_queue.put(full_url)
                self.append_to_sitemap(full_url)
                print(f"Found New Link: {full_url}", flush=True)

    def crawl_worker(self):
        """Worker that processes URLs from the queue"""
        while True:
            try:
                url = self.url_queue.get(timeout=1)  # 1 second timeout
                self.process_url(url)
                self.url_queue.task_done()
            except Empty:  # Fix: use Empty instead of Queue.Empty
                break

    def crawl_parallel(self):
        # Add root URLs to queue
        for url in self.base_urls:
            self.url_queue.put(url)
            self.visited_urls.add(url)

        # Create and start worker threads
        workers = []
       
        future = self.executor.submit(self.crawl_worker)
        workers.append(future)

        # Wait for all workers to complete
        for worker in workers:
            worker.result()
        
        self.executor.shutdown()

    def process_url(self, url):
        if not self.is_valid_url(url) or not self.is_under_root_urls(url):
            return

        with self.semaphore:
            try:
                response = requests.get(url, timeout=10)
                if response.status_code != 200:
                    return

                soup = BeautifulSoup(response.text, 'html.parser')
                with self.url_lock:
                    if url not in self.visited_urls:
                        self.append_to_sitemap(url)

                if not self.should_process_links(url):
                    return

                for link in soup.find_all('a'):
                    href = link.get('href')
                    if not href:
                        continue
                        
                    full_url = urljoin(url, href)
                    if self.is_valid_link_to_crawl(full_url):
                        self.process_found_link(full_url)

            except Exception as e:
                print(f"Error crawling {url}: {str(e)}", file=sys.stderr)

def main():
    parser = argparse.ArgumentParser(description='Web crawler for generating sitemap')
    parser.add_argument('--recursive', '-r', action='store_true',
                      help='Enable recursive crawling (include child links)')
    parser.add_argument('--output', '-o', default='sitemap.xml',
                      help='Output sitemap file name')
    args = parser.parse_args()

    base_urls = [
        "https://www.landui.com/"
    ]
    
    print(f"Starting {'recursive' if args.recursive else 'non-recursive'} crawl for all base URLs")
    crawler = WebCrawler(base_urls, recursive=args.recursive, sitemap_file=args.output)
    crawler.crawl_parallel()
    crawler.finalize_sitemap()  # Close the XML structure
    crawler.executor.shutdown()
    
    print("\nCrawling completed!")
    print(f"Total unique URLs found: {len(crawler.visited_urls)}")
    print(f"Sitemap has been generated: {crawler.sitemap_file}")

if __name__ == "__main__":
    main()