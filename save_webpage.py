#!/usr/bin/env python2
# -*- coding: utf-8 -*-

"""SAVE_WEBPAGE
Save a webpage and all its resource.
"""

import os, sys, re, base64, urlparse, urllib2, urllib, datetime
import argparse
import urltools
import functools
import logging
import codecs

import chardet
from bs4 import BeautifulSoup
import lxml
import requests
import tldextract

__all__ = ['Webpage_Downloader']

__version__ = '1.0'
__license__ = 'The Star And Thank Author License (SATA)'
__author__ = 'Miguel Martinez Lopez'
__url__ = 'https://github.com/python2and3developer/save_webpage'
__source__ = 'https://raw.github.com/python2and3developer/save_webpage/master/save_webpage.py'


logger = logging.getLogger("website_downloader")
formatter = logging.Formatter('%(message)s')
syslog = logging.StreamHandler()
syslog.setFormatter(formatter)
logger.addHandler(syslog)
logger.setLevel(logging.DEBUG)

HTML_FILE = 0
CSS_FILE = 1
FONT_FILE = 2
IMAGE_FILE = 3 
JS_FILE = 4

CSS_URL_RE = re.compile('url\s*\((.+?)\)', re.I)

CONFIDENCE_THRESOLD = 0.7

HTTP_CHARSET_RE = re.compile(r'''charset[ ]?=[ ]?["']?([a-z0-9_-]+)''', re.I)
HTML5_CHARSET_RE = re.compile('<\s*meta[^>]+charset\s*=\s*["\']?([^>]*?)[ /;\'">]'.encode(), re.I)
XHTML_ENCODING_RE = re.compile('^<\?.*encoding=[\'"](.*?)[\'"].*\?>'.encode(), re.I)
CSS_CHARSET_RE = re.compile(r'''@charset\s+["']([-_a-zA-Z0-9]+)["']\;''', re.I)

def is_absolute_url(url):
    return bool(urlparse.urlparse(url).netloc)

def is_absolute_url2(url):
    return re.match(r"""^                    # At the start of the string, ...
                       (?!                  # check if next characters are not...
                          www\.             # URLs starting with www.
                         |
                          (?:http|ftp)s?:// # URLs starting with http, https, ftp, ftps
                         |
                          [A-Za-z]:\\       # Local full paths starting with [drive_letter]:\  
                         |
                          //                # UNC locations starting with //
                       )                    # End of look-ahead check
                       .*                   # Martch up to the end of string""", url, re.X) is not None


def relurl_path(path_url1, path_url2):
    
    if path_url1 != "" and path_url1[0] == "/":
        path_url1 = path_url1[1:]
    
    if path_url2 != "" and path_url2[0] == "/":
        path_url2 = path_url2[1:]
        
    if path_url1 == "":
        if path_url2 == "":
            return "/"
        else:
            return path_url2

    if path_url2 == "":
        depth = path_url2.count("/")
        if depth == 0:
            return "/"            
        else:
            return "../"*depth

    url_parts1 = [x for x in path_url1.split("/") if x]
    url_parts2 = [x for x in path_url2.split("/") if x]


    i = 0
    l = min(len(url_parts1)-1, len(url_parts2)-1)
    
    while True:
        if url_parts1[i] != url_parts2[i]:
            break
        
        if i == l:
            break
        else:
            i += 1

    rel_list = [".."] * (len(url_parts1)-i-1) + url_parts2[i:]
    return "/".join(rel_list)

def absurl(base_url, url):
    parsed_url = urlparse.urlparse(urlparse.urljoin(base_url, url))
    # netloc contains basic auth, so do not use domain
    return urlparse.urlunsplit((
                                parsed_url.scheme, 
                                parsed_url.netloc, 
                                parsed_url.path, 
                                parsed_url.query, 
                                parsed_url.fragment))

def normalize_url(url):
    if url.startswith("//"):
        url = "http:" + url

    url = urllib.quote(url, safe="%/:=&?~#+!$,;'@()*[]")
    url = urltools.normalize(url)
    
    return url

def normalize_codec_name(name):
    '''Return the Python name of the encoder/decoder

    Returns:
        str, None
    '''
    CHARSET_ALIASES = {
        "macintosh": "mac-roman",
        "x-sjis": "shift-jis"
    }

    name = CHARSET_ALIASES.get(name.lower(), name)

    try:
        return codecs.lookup(name).name
    except (LookupError, TypeError, ValueError):
        # TypeError occurs when name contains \x00 (ValueError in Py3.5)
        pass

def try_decoding(data, encoding):
    '''Return whether the Python codec could decode the data.'''
    try:
        data.decode(encoding, 'strict')
    except UnicodeError:
        # Data under 16 bytes is very unlikely to be truncated
        if len(data) > 16:
            for trim in (1, 2, 3):
                trimmed_data = data[:-trim]
                if trimmed_data:
                    try:
                        trimmed_data.decode(encoding, 'strict')
                    except UnicodeError:
                        continue
                    else:
                        return True
        return False
    else:
        return True

def detect_encoding_from_response(response, filetype=None):
    '''Return the likely encoding of the response document.

    Args:
        response (Response): An instance of :class:`.http.Response`.
        is_html (bool): See :func:`.util.detect_encoding`.
        peek (int): The maximum number of bytes of the document to be analyzed.

    Returns:
        ``str``, ``None``: The codec name.
    '''

    content_type = response.headers.get('content-type', '')
    
    # Parse a "Content-Type" string for the document encoding
    http_match = HTTP_CHARSET_RE.search(content_type)

    if http_match:
        http_charset = http_match.group(1)
    else:
        http_charset = None

    content = response.content
    
    if filetype == HTML_FILE:
        if search_entire_document:
            xml_endpos = html_endpos = len(content)
        else:
            xml_endpos = 1024
            html_endpos = max(2048, int(len(content) * 0.05))

        html_encoding = None
        html_encoding_match = XHTML_ENCODING_RE.search(content, endpos=xml_endpos)

        if not html_encoding_match:
            html_encoding_match = HTML5_CHARSET_RE.search(content, endpos=html_endpos)
        if html_encoding_match is not None:
            html_encoding = html_encoding_match.groups()[0].decode(
                'ascii', 'replace')

        if html_encoding is not None:
            html_encoding = normalize_codec_name(html_encoding)

            if try_decoding(raw_data, html_encoding):
                return html_encoding
            else:
                return None

        return None
    elif filetype == CSS_FILE:
        css_encoding_match = CSS_CHARSET_RE.search(content)
        if css_encoding_match:
            css_encoding = css_encoding_match.group(1)
            css_encoding = normalize_codec_name(css_encoding)

            if try_decoding(content, css_encoding):
                return css_encoding
            else:
                return None

    detected_encoding = chardet.detect(content)
    
    if detected_encoding["confidence"] > CONFIDENCE_THRESOLD:
        return detected_encoding["encoding"]
    else:
        logger.info('[ ENCODING NOT DETECTED ] encoding: %s, thresold: %s, url: %s' % (detected_encoding["encoding"], detected_encoding["confidence"], response.url))

    return http_charset

def download_content(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (compatible; MSIE 10.0; Windows NT 6.2; Win64; x64; Trident/6.0)'
    }

    try:
        response = requests.get(url, headers=headers, verify=False)
        logger.info('[ GET ] %d - %s' % (response.status_code, response.url))
        if response.status_code >= 400 or response.status_code < 200:
            response = None
        # elif response.headers.get('content-type', '').lower().startswith('text/'):
        #     content = response.text
        
    except Exception as ex:
        logger.warning('[ DOWNLOAD ERROR ] %s - %s %s' % ('???', url, ex))
        response = None

    return response

def handle_css_content(content, base_url, on_found_url_in_css):
    # Watch out! how to handle urls which contain parentheses inside? Oh god, css does not support such kind of urls
    # I tested such url in css, and, unfortunately, the css rule is broken. LOL!
    # I have to say that, CSS is awesome!

    def replace(matchobj):
        matched_data = matchobj.group(1)
        src = matched_data.strip(' \'"')
        
        if src.startswith("data:"):
            return matched_data

        # if src.lower().endswith('woff') or src.lower().endswith('ttf') or src.lower().endswith('otf') or src.lower().endswith('eot'):
        #     # dont handle font data uri currently
        #     return 'url(' + src + ')'
        url_path = urlparse.urlparse(src).path
        url_path = url_path.lower()

        type_of_resource = None

        if url_path.endswith('.css'):
            type_of_resource = CSS_FILE
        elif url_path.endswith('.png'):
            type_of_resource = IMAGE_FILE
        elif url_path.endswith('.gif'):
            type_of_resource = IMAGE_FILE
        elif url_path.endswith('.jpg') or url_path.endswith('.jpeg'):
            type_of_resource = IMAGE_FILE
        elif url_path.endswith('.svg'):
            type_of_resource = IMAGE_FILE
        elif url_path.endswith('.cur'):
            type_of_resource = IMAGE_FILE
        elif url_path.endswith('.ico'):
            type_of_resource = IMAGE_FILE
        elif url_path.endswith('.ttf'):
            type_of_resource = FONT_FILE
        elif url_path.endswith('.otf'):
            type_of_resource = FONT_FILE
        elif url_path.endswith('.woff'):
            type_of_resource = FONT_FILE
        elif url_path.endswith('.woff2'):
            type_of_resource = FONT_FILE
        elif url_path.endswith('.eot'):
            type_of_resource = FONT_FILE
        elif url_path.endswith('.sfnt'):
            type_of_resource = FONT_FILE
        else:
            logger.warn("Unknown resource "+ matched_data)
            return 'url('+matched_data+')'

        new_src = on_found_url_in_css(type_of_resource, src, base_url=base_url)

        if new_src:
            return 'url('+ new_src + ')'
        else:
            return 'url(' + matched_data + ')'

    content = CSS_URL_RE.sub(replace, content)

    return content

# TODO: Process form actions
# TODO: Provide the possibility to use a custom handler for extra processing the content of internal resources
class Webpage_Downloader(object):

    def __init__(self, output=None):
        if output:
            if os.path.isabs(output):
                self._output = output
            else:
                self._output = os.path.join(os.getcwd(), output)
        else:
            self._output = None

        self.broken_urls = set([])
        self._domain = None

    def _is_absolute_url_in_same_domain(self, url):
        return self._domain == tldextract.extract(url).domain

    def _is_external_resource(self, url):
        if is_absolute_url(url) and not self._is_absolute_url_in_same_domain(url):
            return True
        else:
            return False
        
    def _to_relative_url(self, url):
        """Transforms an absolute url to relative url"""
        
        if not is_absolute_url(url):
            return url
        
        if not self._is_absolute_url_in_same_domain(url):
            return url
        
        parsed_url = urlparse.urlparse(url)

        relative_url = parsed_url.path
        if relative_url.startswith("/"):
            relative_url = relative_url[1:]
        
        return relative_url

    def _save_resource_if_not_exists(self, url, base_url=None, response_handler=None):
        if base_url is not None:
            url = absurl(base_url, url)
        
        url = normalize_url(url)

        relative_url = self._to_relative_url(url)
        
        relative_path_to_resource_file = urllib.url2pathname(relative_url)
        path_to_resource_file = os.path.join(self._output, relative_path_to_resource_file)

        if os.path.isfile(path_to_resource_file):
            logger.info('[ CACHE HIT ] - %s' % url)
        elif url in self.broken_urls:
            logger.info('[ BROKEN URL ] - %s' % url)
        else:
            response = download_content(url)

            if response is None:
                logger.info('[ BROKEN URL ] - %s' % url)
                self.broken_urls.add(url)
                return relative_url
            
            dirname = os.path.dirname(path_to_resource_file)
            if not os.path.isdir(dirname):
                os.makedirs(dirname)
                
            open(path_to_resource_file, 'w').close()
            
            if response_handler is not None:                    
                try:
                    _content = response_handler(response)
                    if _content:
                        content = _content
                    else:
                        content = response.content
                except:
                    os.remove(path_to_resource_file)
                    raise
            else:
                content = response.content

            with open(path_to_resource_file, "w") as f:
                f.write(content)

        return relative_url

    def _on_found_url_in_css(self, internal_urls_in_css, type_of_resource, url, base_url):
        if is_absolute_url(url):
            if self._is_absolute_url_in_same_domain(url):
                path_url1 = urlparse.urlparse(base_url).path
                path_url2 = urlparse.urlparse(url).path

                relative_url = relurl_path(path_url1, path_url2)                
                absoute_url = url
            else:
                return url
        else:
            relative_url = url
            absoute_url = absurl(base_url, url)

        internal_urls_in_css.append((type_of_resource, absoute_url))
            
        return relative_url

    def _create_response_css_handler(self, on_found_url_in_css):       
        def response_css_handler(response):
            encoding = detect_encoding_from_response(response, filetype=CSS_FILE)

            if encoding is None:
                logger.info('[ WARN ] failed to found encoding: %s'%response.url)
                return response.content
            else:
                base_url = response.url

                css = response.content.decode(encoding, 'strict')
                css = handle_css_content(css, base_url=base_url, on_found_url_in_css=on_found_url_in_css)
                css = css.encode("utf-8")

                return css

        return response_css_handler
    
    def _apply_replacements_to_text(self, text, replacements):
        for old, new in replacements:
            text.replace(old, new)
        return text

    def _response_js_handler(self, response, javascript_replacements):
        encoding = detect_encoding_from_response(response)
        content = response.content.decode(encoding, 'strict')
        
        content = self._apply_replacements_to_text(content, javascript_replacements)
        
        content = content.encode("utf-8")
        return content      

    def save(self, url, html_replacements=None, javascript_replacements=None):
        # It should return a list of links found in the html
        '''
        given a url url such as http://www.google.com, http://custom.domain/url.html
        return saved single html
        '''
        
        if not is_absolute_url(url):
            raise Exception("URL is not absolute: %s"%url)

        if self._domain is None:
            self._domain = tldextract.extract(url).domain
            if self._output is None:
                self._output = os.path.join(os.getcwd(), urlparse.urlparse(url).netloc)
        else:
            if not self._is_absolute_url_in_same_domain(url):
                raise Exception("URL not in the same domain: %s"%url)

        if os.path.exists(self._output):
            if not os.path.isdir(self._output):
                raise Exception("It's not possible to save webpage in 'output' directory")
        else:
            os.makedirs(self._output)

        parsed_url = urlparse.urlparse(url)
        
        base_url_path = parsed_url.path

        if base_url_path.endswith("/") or base_url_path == "":
            base_url_path += "index.html"

        if base_url_path.startswith("/"):
            base_url_path = base_url_path[1:]

        relative_path_to_html_file = os.path.join(*base_url_path.split("/"))
        path_to_html_file = os.path.join(self._output, relative_path_to_html_file)

        base_url = urlparse.urlunparse((parsed_url.scheme, parsed_url.netloc, base_url_path, "", "", ""))

        response = download_content(url)

        if response is None:
            raise Exception("Not possible to download: %s"%url)
        
        html = response.content

        # now build the dom tree
        soup = BeautifulSoup(html, 'lxml')

        logger.info("\nProcessing script's..")

        if javascript_replacements:
            response_js_handler = functols.partial(self._response_js_handler, javascript_replacements=javascript_replacements)
        else:
            response_js_handler = None

        for js in soup('script'):
            if not js.get('src'): continue       
            src = js['src']
            
            if not self._is_external_resource(src):
                relative_src = self._save_resource_if_not_exists(src, base_url=base_url, response_handler=response_js_handler)
                
                src = relurl_path(base_url_path, relative_src)

                js['src'] = src

        logger.info("\nProcessing img's...")

        for img in soup('img'):
            if not img.get('src'): continue
            src = img['src']

            if not self._is_external_resource(src):
                relative_src = self._save_resource_if_not_exists(src, base_url=base_url)
                src = relurl_path(base_url_path, relative_src)

                img['src'] = src

        current_path = urlparse.urlparse(url).path

        logger.info("\nProcessing links...")
        for a in soup.find_all('a', href=True):
            href = a['href'].strip()

            if not href.startswith('#'):
                href = absurl(base_url, href)
                href = normalize_url(href)

                if self._is_external_resource(href):
                    a['href'] = href
                else:
                    parsed_href = urlparse.urlparse(href)
                    new_href_path = relurl_path(base_url_path, parsed_href.path)
                    
                    a['href'] = urlparse.urlunsplit(("", "", new_href_path, parsed_href.query, parsed_href.fragment))

        internal_urls_in_css = []

        logger.info("\nProcessing link elements...")
        for link in soup('link'):
            if link.get('href'):
                href = link['href']
                
                href = absurl(base_url, href)
                href = normalize_url(href)

                if self._is_external_resource(href):
                    link['href'] = href
                else:
                    if (link.get('type') == 'text/css' or link['href'].lower().endswith('.css') or 'stylesheet' in (link.get('rel') or [])):
                        internal_urls_in_css.append((CSS_FILE, href))

                    relative_href = self._to_relative_url(href)
                    href = relurl_path(base_url_path, relative_href)

                    link['href'] = href

            else:
                if link.has_attr('type') and link['type'] == 'text/css':
                    if link.string:
                        link.string = handle_css_content(link.string, base_url=base_url, on_found_url_in_css=on_found_url_in_css)

        on_found_url_in_css = functools.partial(self._on_found_url_in_css, internal_urls_in_css)
        response_css_handler = self._create_response_css_handler(on_found_url_in_css)

        logger.info("\nProcessing style elements...")
        for style in soup.find_all('style'):
            if style.string.strip():
                style.string = handle_css_content(style.string, base_url=base_url, on_found_url_in_css=on_found_url_in_css)

        for tag in soup(True):
            if tag.has_attr('style'):
                if tag['style']:
                    tag['style'] = handle_css_content(tag['style'], base_url=base_url, on_found_url_in_css=on_found_url_in_css)

        logger.info("\nProcessing internal resources found in stylesheets...")
        while len(internal_urls_in_css) != 0:
            type_of_resource, internal_url = internal_urls_in_css.pop()

            if type_of_resource == CSS_FILE:
                self._save_resource_if_not_exists(internal_url, response_handler=response_css_handler)
            else:
                self._save_resource_if_not_exists(internal_url)

        html = str(soup)
        if html_replacements:
            self._apply_replacements_to_text(html, html_replacements)

        with open(path_to_html_file, "w") as f:
            f.write(html)


def main():
    parser = argparse.ArgumentParser(description=__doc__, epilog="""save_webpage.py:
    Takes a url and extracts that website with all its internal resource files.
    Transforms all internal resources so that they link to local files.
    Process css files exctracting new resource and converting url's.
    Possibility to replace javascript and html files using custom substitutions.
    Full Unicode/UTF-8 support.""")
    parser.add_argument('--version', action='version', version=__version__)
    parser.add_argument('-q', '--quite', action='store_true', help="don't show verbose url get log in stderr")
    parser.add_argument('--insecure', action='store_true', help="Ignore the certificate")
    parser.add_argument('-i', '--url-list', action='store', help="Path to file containing list of url's")
    parser.add_argument('-o', '--output', action='store', default=None, help="Output directory")
    parser.add_argument('--javascript-replacements', action='store', default=None, help="Path to file containing javascript replacements in JSON format")
    parser.add_argument('--html-replacements', action='store', default=None, help="Path to file containing html replacements in JSON format")
    parser.add_argument('-b', '--base-url', action='store', help="Resolves relative links using URL as the point of reference")
    parser.add_argument("url", nargs='?', help="the website to store")
    args = parser.parse_args()

    output = args.output
    base_url = args.base_url
    
    javascript_replacements = args.javascript_replacements
    if javascript_replacements:
        with open(javascript_replacements) as f:
            javascript_replacements = json.loads(f.read())
    
    html_replacements = args.html_replacements
    if html_replacements:
        with open(html_replacements) as f:
            html_replacements = json.loads(f.read())

    if args.url_list:
        
        with open(args.url_list, "r") as f:
            url_list = [l for l in f.read().splitlines() if l.strip() != ""]

        if len(url_list) != 0:
            webpage_downloader = Webpage_Downloader(output=output)

            for url in url_list:
                webpage_downloader.save(
                                url, 
                                javascript_replacements=javascript_replacements,
                                html_replacements=html_replacements)
            
    else:
        webpage_downloader = Webpage_Downloader(output=output)
        webpage_downloader.save(
                args.url, 
                javascript_replacements=javascript_replacements,
                html_replacements=html_replacements)

if __name__ == '__main__':
    main()
