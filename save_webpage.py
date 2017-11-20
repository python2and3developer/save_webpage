#!/usr/bin/env python2
# -*- coding: utf-8 -*-

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
    new = urlparse.urlparse(urlparse.urljoin(base_url, url))
    # netloc contains basic auth, so do not use domain
    return urlparse.urlunsplit((new.scheme, new.netloc, new.path, new.query, ''))

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


class Webpage_Downloader(object):

    def __init__(self, domain, output=None, base_url=None, javascript_replacements=None, prettify=False, minify=True):
        if output:
            if os.path.isabs(output):
                self._output = output
            else:
                self._output = os.path.join(os.getcwd(), output)
        else:
            self._output = os.getcwd()

        self._domain = domain

        self._base_url = base_url
        self._prettify = prettify
        
        self._javascript_replacements = javascript_replacements
        
        self.broken_urls = set([])
        
    def _is_in_same_domain(self, url):
        return self._domain == tldextract.extract(url).domain
        
    def _local_url(self, url, base_url=None):
        if base_url is not None:
            url = absurl(base_url, url)
        
        url = normalize_url(url)
        parsed_url = urlparse.urlparse(url)

        if not self._is_in_same_domain(url):
            return url
        
        relative_url = parsed_url.path
        
        if self._base_url is not None:
            relative_url = urlparse.urljoin(self._base_url, relative_url)
            
        if relative_url.startswith("/"):
            relative_url = relative_url[1:]
        
        return relative_url

    def _save_resource_if_not_exists(self, url, base_url=None, response_handler=None):
        if base_url is not None:
            url = absurl(base_url, url)
        
        url = normalize_url(url)

        relative_url = self._local_url(url)
        
        relative_path_to_resource_file = urllib.url2pathname(relative_url)
        if relative_path_to_resource_file.startswith("/"):
            relative_path_to_resource_file = relative_path_to_resource_file[1:]

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
                    content = response_handler(response)
                    #content = on_found_url_in_css(content, possible_encoding)
                except:
                    os.remove(path_to_resource_file)
                    raise
            else:
                content = response.content

            with open(path_to_resource_file, "w") as f:
                f.write(content)

        return relative_url

    # Lo del URL require revision
    # Modificar la variable output
    def save(self, url):
        # It should return a list of links found in the html
        '''
        given a url url such as http://www.google.com, http://custom.domain/url.html
        return saved single html
        '''

        if os.path.exists(self._output):
            if not os.path.isdir(self._output):
                raise Exception("It's not possible to create output file")
        else:
            os.makedirs(self._output)

        url_path = urlparse.urlparse(url).path
        if url_path == "" or url_path == "/":
            path_to_resource_file = os.path.join(self._output, "index.html")
        else:
            if url_path[0] == "/":
                url_path = url_path[1:]
            
            relative_path_to_resource_file = os.path.join(*url_path.split("/"))
            path_to_resource_file = os.path.join(self._output, relative_path_to_resource_file)

        base_url = url
        response = download_content(url)

        if response is None: return
        
        html = response.content

        # now build the dom tree
        soup = BeautifulSoup(html, 'lxml')
                
        if self._javascript_replacements is None:
            process_replacements= None
        else:
            def process_replacements(response):

                encoding = detect_encoding_from_response(response, filetype=CSS_FILE)
                content = response.content.decode(encoding, 'strict')
                
                for old, new in self._javascript_replacements:
                    content.replace(old, new)
                
                content = content.encode("utf-8")
                return content        

        for js in soup('script'):
            if not js.get('src'): continue       
            src = js['src']

            new_src = self._save_resource_if_not_exists(src, base_url=url, response_handler=process_replacements)
            
            js['src'] = new_src

        for img in soup('img'):
            if not img.get('src'): continue
            src = img['src']

            new_src = self._save_resource_if_not_exists(src, base_url=url)
            
            img['src'] = new_src

        current_path = urlparse.urlparse(url).path

        for a in soup.find_all('a', href=True):
            href = a['href'].strip()
            if not href.startswith('#'):
                if is_absolute_url(href) and self._is_in_same_domain(href):                        
                    parsed_href = urlparse.urlparse(href)
                    new_path = relurl_path(current_path, parsed_href.path)
                    
                    a['href'] = urlparse.urlunsplit(("", "", new_path, parsed_href.query, parsed_href.fragment))

        external_urls_in_css = []

        def on_found_url_in_css(type_of_resource, external_url, base_url):
            if is_absolute_url(external_url):
                if self._is_in_same_domain(external_url):
                    path_url1 = urlparse.urlparse(base_url).path
                    path_url2 = urlparse.urlparse(external_url).path

                    relative_external_url = relurl_path(path_url1, path_url2)                
                    absoute_external_url = external_url
                else:
                    return external_url
            else:
                relative_external_url = external_url
                absoute_external_url = absurl(base_url, external_url)

            external_urls_in_css.append((type_of_resource, absoute_external_url))
                
            return relative_external_url
        
        def process_css_content_from_response(response):
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

        for link in soup('link'):
            if link.get('href'):
                href = link['href']
                href = absurl(base_url, href)

                if (link.get('type') == 'text/css' or link['href'].lower().endswith('.css') or 'stylesheet' in (link.get('rel') or [])):

                    local_url = self._local_url(href)
                    link['href'] = local_url

                    if self._is_in_same_domain(href):
                        external_urls_in_css.append((CSS_FILE, href))
                else:
                    link['href'] = href
            else:
                if link.has_attr('type') and link['type'] == 'text/css':
                    if link.string:
                        link.string = handle_css_content(link.string, base_url=base_url, on_found_url_in_css=on_found_url_in_css)

        for style in soup.find_all('style'):
            if style.string.strip():
                style.string = handle_css_content(style.string, base_url=base_url, on_found_url_in_css=on_found_url_in_css)

        for tag in soup(True):
            if tag.has_attr('style'):
                if tag['style']:
                    tag['style'] = handle_css_content(tag['style'], base_url=base_url, on_found_url_in_css=on_found_url_in_css)


        while len(external_urls_in_css) != 0:
            type_of_resource, external_url = external_urls_in_css.pop()

            if type_of_resource == CSS_FILE:
                self._save_resource_if_not_exists(external_url, response_handler=process_css_content_from_response)
            else:
                self._save_resource_if_not_exists(external_url)

        if self._prettify:
            html = soup.prettify(formatter='html')
        else:
            html = str(soup)
        
        with open(path_to_resource_file, "w") as f:
            f.write(html)


def usage():
    print("""
usage:

    $ save [options] some_url

options:

    -h, --help              help page, you are reading this now!
    -q, --quite             don't show verbose url get log in stderr

examples:

    $ save -h
        you are reading this help message

    $ save http://www.google.com > google.html
        save google url page for offline reading, keep style untainted

    $ save http://gabrielecirulli.github.io/2048/ > 2048.html
        save dynamic page with Javascript example
        the 2048 game can be played offline after being saved

    $ save /path/to/xxx.html > xxx_single.html
        combine local saved xxx.html with a directory named xxx_files together into a single html file
""")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-q', '--quite', action='store_true', help="don't show verbose url get log in stderr")
    parser.add_argument('-k', '--insecure', action='store_true', help="ignore the certificate")
    parser.add_argument('-i', '--url-list', action='store', help="Path to file containing list of url's")
    parser.add_argument('-o', '--output', action='store', default=None, help="Output directory")
    parser.add_argument('--replacements', action='store', default=None, help="Output directory")
    parser.add_argument('-B', '--base-url', action='store', help="Resolves relative links using URL as the point of reference")
    parser.add_argument("url", nargs='?', help="the website to store")
    args = parser.parse_args()

    if args.url_list:
        
        with open(args.url_list, "r") as f:
            url_list = [l for l in f.read().splitlines() if l.strip() != ""]

        if len(url_list) != 0:
            domain = tldextract.extract(url_list[0]).domain
            webpage_downloader = Webpage_Downloader(
                                domain,
                                args.output,
                                base_url=args.base_url)

            for url in url_list:
                webpage_downloader.save(url)
            
    else:
        domain = tldextract.extract(args.url).domain
        
        webpage_downloader = Webpage_Downloader(
                    domain,
                    args.output,
                    base_url=args.base_url)
        webpage_downloader.save(args.url)

if __name__ == '__main__':
    main()
