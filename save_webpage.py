#!/usr/bin/env python2
# -*- coding: utf-8 -*-

"""Save_Webpage
Save webpages and all its resources. Apply search and replace of matched strings.
"""

import os
import sys
import re
import base64
import urlparse
import urllib2
import urllib
import json
import argparse
import urltools
import functools
import logging
import codecs
import datetime

import chardet
from bs4 import BeautifulSoup
import lxml
import requests
import tldextract

__all__ = ['Save_Webpage']

__version__ = '2.0'
__license__ = 'The Star And Thank Author License (SATA)'
__author__ = 'Miguel Martinez Lopez'
__url__ = 'https://github.com/python2and3developer/save_webpage'
__source__ = 'https://raw.github.com/python2and3developer/save_webpage/master/save_webpage.py'


logger = logging.getLogger("Save_Webpage")
formatter = logging.Formatter('%(message)s')
syslog = logging.StreamHandler()
syslog.setFormatter(formatter)
logger.addHandler(syslog)
logger.setLevel(logging.DEBUG)

HTML_FILE = 0
CSS_FILE = 1
IMAGE_FILE = 2
AUDIO_FILE = 3
VIDEO_FILE = 4
FONT_FILE = 5
JS_FILE = 6
XML_FILE = 7
OTHER_RESOURCE = 8

CSS_URL_RE = re.compile('url\s*\((.+?)\)', re.I)

CONFIDENCE_THRESOLD = 0.7

HTTP_CHARSET_RE = re.compile(r'''charset[ ]?=[ ]?["']?([a-z0-9_-]+)''', re.I)
HTML5_CHARSET_RE = re.compile('<\s*meta[^>]+charset\s*=\s*["\']?([^>]*?)[ /;\'">]'.encode(), re.I)
XHTML_ENCODING_RE = re.compile('^<\?.*encoding=[\'"](.*?)[\'"].*\?>'.encode(), re.I)
CSS_CHARSET_RE = re.compile(r'''@charset\s+["']([-_a-zA-Z0-9]+)["']\;''', re.I)

# https://stackoverflow.com/questions/2725156/complete-list-of-html-tag-attributes-which-have-a-url-value

TAGS_ATTRS_WITH_URLS = {
    'a'            : [ 'href', 'urn' ],
    'base'         : [ 'href' ],
    'form'         : [ 'action', 'data' ],
    'img'          : [ 'src', 'usemap', 'longdesc', 'dynsrc', 'lowsrc', 'srcset' ],
    'amp-img'      : [ 'src', 'srcset' ],
    'link'         : [ 'href' ],

    'applet'       : [ 'code', 'codebase', 'archive', 'object' ],
    'area'         : [ 'href' ],
    'body'         : [ 'background', 'credits', 'instructions', 'logo' ],
    'input'        : [ 'src', 'usemap', 'dynsrc', 'lowsrc', 'action', 'formaction' ],

    'blockquote'   : [ 'cite' ],
    'del'          : [ 'cite' ],
    'frame'        : [ 'longdesc', 'src' ],
    'head'         : [ 'profile' ],
    'iframe'       : [ 'longdesc', 'src' ],
    'ins'          : [ 'cite' ],
    'object'       : [ 'archive', 'classid', 'codebase', 'data', 'usemap' ],
    'q'            : [ 'cite' ],
    'script'       : [ 'src' ],

    'audio'        : [ 'src' ],
    'command'      : [ 'icon' ],
    'embed'        : [ 'src', 'code', 'pluginspage' ],
    'event-source' : [ 'src' ],
    'html'         : [ 'manifest', 'background', 'xmlns' ],
    'source'       : [ 'src' ],
    'video'        : [ 'src', 'poster' ],

    'bgsound'      : [ 'src' ],
    'div'          : [ 'href', 'src' ],
    'ilayer'       : [ 'src' ],
    'table'        : [ 'background' ],
    'td'           : [ 'background' ],
    'th'           : [ 'background' ],
    'layer'        : [ 'src' ],
    'xml'          : [ 'src' ],

    'button'       : [ 'action', 'formaction' ],
    'datalist'     : [ 'data' ],
    'select'       : [ 'data' ],

    'access'       : [ 'path' ],
    'card'         : [ 'onenterforward', 'onenterbackward', 'ontimer' ],
    'go'           : [ 'href' ],
    'option'       : [ 'onpick' ],
    'template'     : [ 'onenterforward', 'onenterbackward', 'ontimer' ],
    'wml'          : [ 'xmlns' ]
}


ATTRS_WITH_EXTERNAL_RESOURCES = {
    ("a", "href"): HTML_FILE,
    ("script", "src"): JS_FILE,
    ("img", "src"): IMAGE_FILE,
    ("frame", "src"): HTML_FILE,
    ("iframe", "src"): HTML_FILE,
    ("audio", "src"): AUDIO_FILE,
    ("bgsound", "src"): AUDIO_FILE,
    ("video", "src"): VIDEO_FILE
}


def is_absolute_url(url):
    return bool(urlparse.urlparse(url).netloc)

def is_absolute_url2(url):
    return re.match(r"""^                    # At the start of the string, ...
                       (?:                  # check if next characters are ...
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


def is_subpath(path, parent):
    '''
    Returns True if *path* points to the same or a subpath of *parent*.
    '''

    try:
        relpath = os.path.relpath(path, parent)
    except ValueError:
        return False  # happens on Windows if drive letters don't match
    return relpath == os.curdir or not relpath.startswith(os.pardir)


def absurl(base_url, url):
    parsed_url = urlparse.urlparse(urlparse.urljoin(base_url, url))
    # netloc contains basic auth, so do not use domain
    return urlparse.urlunsplit((
                                parsed_url.scheme,
                                parsed_url.netloc,
                                parsed_url.path,
                                parsed_url.query,
                                parsed_url.fragment))

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


def detect_encoding_from_http_response(response, filetype=None, search_entire_document=True):
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
            xhtml_endpos = html_endpos = len(content)
        else:
            xhtml_endpos = 1024
            html_endpos = max(2048, int(len(content) * 0.05))

        html_encoding = None
        html_encoding_match = XHTML_ENCODING_RE.search(content, endpos=xhtml_endpos)

        if not html_encoding_match:
            html_encoding_match = HTML5_CHARSET_RE.search(content, endpos=html_endpos)
        if html_encoding_match is not None:
            html_encoding = html_encoding_match.groups()[0].decode(
                'ascii', 'replace')

        if html_encoding is not None:
            html_encoding = normalize_codec_name(html_encoding)

            if try_decoding(content, html_encoding):
                return html_encoding
            else:
                return None

    elif filetype == CSS_FILE:
        css_encoding_match = CSS_CHARSET_RE.search(content)
        if css_encoding_match:
            encoding = css_encoding_match.group(1)
            encoding = normalize_codec_name(encoding)

            if try_decoding(content, encoding):
                return encoding
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


def resource_type_using_extension(url):
    url_path = urlparse.urlparse(url).path
    url_path = url_path.lower()

    if url_path.endswith('.html') or url_path.endswith('.htm'):
        return HTML_FILE
    elif url_path.endswith('.js'):
        return JS_FILE
    elif url_path.endswith('.css'):
        return CSS_FILE
    elif url_path.endswith('.png'):
        return IMAGE_FILE
    elif url_path.endswith('.gif'):
        return IMAGE_FILE
    elif url_path.endswith('.jpg') or url_path.endswith('.jpeg'):
        return IMAGE_FILE
    elif url_path.endswith('.svg'):
        return IMAGE_FILE
    elif url_path.endswith('.cur'):
        return IMAGE_FILE
    elif url_path.endswith('.ico'):
        return IMAGE_FILE
    elif url_path.endswith('.ttf'):
        return FONT_FILE
    elif url_path.endswith('.otf'):
        return FONT_FILE
    elif url_path.endswith('.woff'):
        return FONT_FILE
    elif url_path.endswith('.woff2'):
        return FONT_FILE
    elif url_path.endswith('.eot'):
        return FONT_FILE
    elif url_path.endswith('.sfnt'):
        return FONT_FILE
    else:
        return None


def process_urls_in_css_content(content, url_handler, replace=True):
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

        type_of_resource = resource_type_using_extension(src)

        if type_of_resource == None:
            logger.warn("Unknown resource "+ matched_data)
            return 'url('+matched_data+')'
        else:
            new_src = url_handler(type_of_resource, src)

            if new_src:
                return 'url('+ new_src + ')'
            else:
                return 'url(' + matched_data + ')'

    content = CSS_URL_RE.sub(replace, content)

    return content


def process_urls_in_html_content(content, url_handler, replace=True):
    # now build the dom tree
    soup = BeautifulSoup(content, "html5lib")

    for tag_name, attrs in TAGS_ATTRS_WITH_URLS.items():
        list_of_tags = soup.find_all(tag_name)

        number_of_tags = len(list_of_tags)
        if number_of_tags == 0: continue

        logger.info("\nProcessing %d %s's.."%(number_of_tags, tag_name))

        if tag_name == "link":
            for link in list_of_tags:
                if not link.get('href'): continue

                href = link['href']

                if (link.get('type') == 'text/css' or link['href'].lower().endswith('.css') or 'stylesheet' in (link.get('rel') or [])):
                    href = url_handler(CSS_FILE, href)
                else:
                    href = url_handler(OTHER_RESOURCE, href)

                if href:
                    link['href'] = href
        elif tag_name == "style":
            for style in list_of_tags:
                if style.string.strip():
                    style.string = process_urls_in_css_content(style.string, url_handler=url_handler)

        else:
            for tag in list_of_tags:
                for attribute_name in attrs:
                    if tag.has_attr(attribute_name):

                        if (tag_name, attribute_name) in ATTRS_WITH_EXTERNAL_RESOURCES:
                            type_of_resource = ATTRS_WITH_EXTERNAL_RESOURCES[tag_name, attribute_name]
                        else:
                            type_of_resource = OTHER_RESOURCE

                        # srcset is a fair bit different from most html
                        # attributes, so it gets it's own processsing
                        if attribute_name == 'srcset':
                            srcset = tag[attribute_name]

                            list_of_new_urls_and_descriptors = []
                            is_srcset_modified = False


                            for url_and_descriptor in srcset.split(","):
                                # remove the (optional) descriptor
                                # https://developer.mozilla.org/en-US/docs/Web/HTML/Element/img#attr-srcset
                                url_and_descriptor = url_and_descriptor.strip()

                                match = re.search(r'\s+[\d\.]+[xw]\s*$', url_and_descriptor)

                                if match:
                                    descriptor = match.group(0)
                                    url = url_and_descriptor[:match.start()]
                                else:
                                    descriptor = ""
                                    url = url_and_descriptor

                                new_url = url_handler(type_of_resource, url)
                                if new_url:
                                    list_of_new_urls_and_descriptors.append(new_url + descriptor)
                                    is_srcset_modified = True
                                else:
                                    list_of_new_urls_and_descriptors.append(url + descriptor)

                            if is_srcset_modified:
                                tag["srcset"] = ",".join(list_of_new_urls_and_descriptors)
                        else:

                            url = tag[attribute_name]
                            url = url_handler(type_of_resource, url)

                            if url:
                                tag[attribute_name] = url

    for tag in soup(True):
        if tag.has_attr('style'):
            style = tag['style'].strip()

            if style:
                tag['style'] = process_urls_in_css_content(style, url_handler=url_handler)

    return unicode(soup)


def empty_file(file_path):
    dirname = os.path.dirname(file_path)
    if not os.path.isdir(dirname):
        os.makedirs(dirname)

    open(file_path, 'w').close()


# TODO: Process form actions
# TODO: Provide the possibility to use a custom handler for extra processing the content of internal resources
class Save_Webpage(object):
    RELATIVE_MODE = 0
    ABSOLUTE_MODE = 1
    NO_CHANGE_MODE = 2


    def __init__(self, list_of_seed_urls, forbidden_urls=None, follow_links=False, replacements=None, domain=None, output=None, base_url=None, mode=NO_CHANGE_MODE, default_file="index.html"):
        if not list_of_seed_urls:
            raise Exception("List of seed url's can't be empty")

        self._list_of_seed_urls = list_of_seed_urls

        self._broken_urls = set([])

        self._queue = []

        for url in list_of_seed_urls:
            if not is_absolute_url(url):
                raise Exception("Seed URL is not absolute: %s"%url)

            url = self._normalize_url(url, default_file=default_file)
            path_to_resource_file = self._path_to_resource_file(url, output=output)

            empty_file(path_to_resource_file)

            self._queue.append((HTML_FILE, url))


        if domain is None:
            url = list_of_seed_urls[0]
            domain = tldextract.extract(url).domain

        self._domain = domain

        if output is None:
            url = list_of_seed_urls[0]
            output = os.path.join(os.getcwd(), urlparse.urlparse(url).netloc)
        else:
            if not os.path.isabs(output):
                output = os.path.join(os.getcwd(), output)

        self._output = output

        if forbidden_urls:
            forbidden_urls = [normalize_url(url) for url in forbidden_urls]

        self._forbidden_urls = forbidden_urls
        self._follow_links = follow_links

        if mode != self.RELATIVE_MODE \
            and mode != self.ABSOLUTE_MODE \
            and mode != self.NO_CHANGE_MODE:
            raise Exception("Invalid mode")

        self._mode = mode

        if base_url:
            if not (base_url.startswith("http://") or base_url.startswith("https://")):
                raise Exception("Base URL requires the protocol")
        else:
            if mode == self.ABSOLUTE_MODE:
                raise Exception("Base URL is require to convert all url's to absolute")

        self._base_url = base_url
        self._default_file = default_file
        self._replacements = replacements

    def _is_absolute_url_in_same_domain(self, url):
        return self._domain == tldextract.extract(url).domain

    def _is_external_resource(self, url):
        if is_absolute_url(url) and not self._is_absolute_url_in_same_domain(url):
            return True
        else:
            return False

    # Esta parte require revision
    @staticmethod
    def _normalize_url(url, default_file="index.html"):
        if url.startswith("//"):
            url = "http:" + url

        parsed_url = urlparse.urlparse(url)

        if parsed_url.path.endswith("/") or parsed_url.path == "":
            url_path = parsed_url.path + default_file
        else:
            url_path = parsed_url.path

        url = urlparse.urlunparse((parsed_url.scheme, parsed_url.netloc, url_path, "", "", ""))

        url = urllib.quote(url, safe="%/:=&?~#+!$,;'@()*[]")
        url = urltools.normalize(url)

        return url

    @staticmethod
    def _path_to_resource_file(url, output):
        parsed_url = urlparse.urlparse(url)
        url_path = parsed_url.path

        if url_path.startswith("/"):
            url_path = url_path[1:]

        relative_path_to_resource_file = urllib.url2pathname(url_path)
        path_to_resource_file = os.path.join(output, relative_path_to_resource_file)

        return path_to_resource_file

    def _replace_content(self, current_url, content):
        if not self._replacements: return content

        url_path = urlparse.urlparse(current_url).path

        for pattern_url_path, list_of_replacement_objs in self._replacements:
            is_url_matched = re.match(pattern_url_path, url_path)
            if is_url_matched:
                for replacement_obj in list_of_replacement_objs:
                    if callable(replacement_obj):
                        content = replacement_obj(content)
                    else:
                        pattern_text, substitution = replacement_obj
                        content = re.sub(pattern_text, substitution, content)
                break

        return content

    def _on_extracted_url(self, type_of_resource, url, base_url):
        if type_of_resource == HTML_FILE and not self._follow_links: return

        original_url = url

        if base_url is not None:
            url = absurl(base_url, url)

        url = self._normalize_url(url, default_file=self._default_file)

        if self._is_external_resource(url): return
        if self._forbidden_urls and url in self._forbidden_urls: return

        if url in self._broken_urls:
            logger.info('[ BROKEN URL ] - %s' % url)
            return


        path_to_resource_file = self._path_to_resource_file(url, output=self._output)

        if os.path.isfile(path_to_resource_file):
            logger.info('[ CACHE HIT ] - %s' % url)
            return

        empty_file(path_to_resource_file)

        self._queue.append((type_of_resource, url))

        if self._mode == self.ABSOLUTE_MODE:
            if is_absolute_url2(original_url):
                parsed_original_url = urlparse.urlparse(original_url)

                url = urlparse.urljoin(self._base_url,
                                       urlparse.urlunparse((
                                                           "",
                                                           "",
                                                           parsed_original_url.path,
                                                           parsed_original_url.params,
                                                           parsed_original_url.query,
                                                           parsed_original_url.fragment))
                                      )
            else:
                url = urlparse.urljoin(self._base_url, original_url)

        elif self._mode == self.RELATIVE_MODE:
            if is_absolute_url2(original_url):
                parsed_original_url = urlparse.urlparse(original_url)

                url_path = relurl_path(urlparse.urlparse(base_url).path, parsed_original_url.path)
                url = urlparse.urlunparse((
                                   "",
                                   "",
                                   url_path,
                                   parsed_original_url.params,
                                   parsed_original_url.query,
                                   parsed_original_url.fragment))

                if url[0] == "/": url = url[1:]
            else:
                url = original_url
        else:
            return

        return url


    def start(self):
        if os.path.exists(self._output):
            if not os.path.isdir(self._output):
                raise Exception("It's not possible to save webpage in 'output' directory")
        else:
            os.makedirs(self._output)

        i = 0

        while len(self._queue) != 0:
            type_of_resource, url = self._queue.pop()

            path_to_resource_file = self._path_to_resource_file(url, output=self._output)

            response = download_content(url)

            if response is None:
                logger.info('[ BROKEN URL ] - %s' % url)
                self._broken_urls.add(url)

                if os.path.isfile(path_to_resource_file):
                    os.remove(path_to_resource_file)

                continue

            content = response.content

            base_url = url

            def url_handler(type_of_resource, url):
                return self._on_extracted_url(type_of_resource, url, base_url)

            if type_of_resource == HTML_FILE:
                soup = BeautifulSoup(content, "html5lib")
                html_base = soup.find("base", href=True)

                if html_base:
                    base_url = html_base["href"]
                    if not is_absolute_url2(base_url):
                        base_url = urlparse.urljoin(url, base_url)

                encoding = detect_encoding_from_http_response(response, filetype=HTML_FILE)

                content = content.decode(encoding, 'strict')
                if self._mode == self.NO_CHANGE_MODE:
                    process_urls_in_html_content(content, url_handler)
                else:
                    content = process_urls_in_html_content(content, url_handler)

                content = self._replace_content(url, content)
                content = content.encode(encoding)

            elif type_of_resource == CSS_FILE:
                encoding = detect_encoding_from_http_response(response, filetype=CSS_FILE)

                content = content.decode(encoding, 'strict')

                if self._mode == self.NO_CHANGE_MODE:
                    content = process_urls_in_css_content(content, url_handler)
                else:
                    process_urls_in_css_content(content, url_handler)

                content = self._replace_content(url, content)
                content = content.encode(encoding)

            elif type_of_resource == JS_FILE:
                content = self._replace_content(url, content)

            with open(path_to_resource_file, "w") as f:
                f.write(content)


def main():
    parser = argparse.ArgumentParser(description=__doc__, epilog="""save_webpage.py:
    Takes a url and extracts that website with all its internal resource files.
    Transforms all internal resources so that they link to local files.
    Process css files exctracting new resource and converting url's.
    Possibility to replace javascript and html files using custom substitutions.
    Full Unicode/UTF-8 support.""")
    parser.add_argument('--version', action='version', version=__version__)
    parser.add_argument('-q', '--quite', action='store_true', default=False, help="don't show verbose url get log in stderr")
    parser.add_argument('--insecure', action='store_true', default=False, help="Ignore the certificate")

    parser.add_argument("list_of_seed_urls", nargs='*', help="Seed urls")
    parser.add_argument("--forbidden-urls", nargs='+', help="Forbidden urls")
    parser.add_argument('--follow-links', action='store_true', default=False, help="Follow links")
    parser.add_argument('-o', '--output', action='store', default=None, help="Output directory")
    parser.add_argument('-b', '--base-url', action='store', help="Resolves relative links using URL as the point of reference")
    parser.add_argument('--default-file', action='store', default="index.html", help="Default index file")
    parser.add_argument('--mode', action='store',  default="relative", choices=["relative", "absolute", "nochange"], help="Mode of extraction")
    parser.add_argument('--config', action='store', dest="path_to_config_file", help="Path to configuration file")
    args = parser.parse_args()

    output = args.output
    base_url = args.base_url
    follow_links = args.follow_links
    forbidden_urls = args.forbidden_urls
    list_of_seed_urls  = args.list_of_seed_urls
    mode = args.mode
    default_file = args.default_file


    if mode == "relative":
        mode = Save_Webpage.RELATIVE_MODE
    elif mode == "absolute":
        mode = Save_Webpage.ABSOLUTE_MODE
    else:
        mode = Save_Webpage.NO_CHANGE_MODE

    replacements = None

    if args.path_to_config_file:
        config = json.parse(args.path_to_config_file)
        if "base_url" in config:
            base_url = config["base_url"]

        if "follow_links" in config:
            follow_links = config["follow_links"]

        if "forbidden_urls" in config:
            forbidden_urls = config["forbidden_urls"]

        if "replacements" in config:
            replacements = config["replacements"]

        if "output" in config:
            output = config["output"]

        if "list_of_seed_urls" in config:
            list_of_seed_urls = config["list_of_seed_urls"]

        if "default_file" in config:
            default_file = config["default_file"]

        if "mode" in config:
            mode = config["mode"]


    save_webpage = Save_Webpage(
                            list_of_seed_urls=list_of_seed_urls,
                            output=output,
                            follow_links=follow_links,
                            forbidden_urls=forbidden_urls,
                            replacements=replacements,
                            base_url=base_url,
                            mode = mode,
                            default_file=default_file)
    save_webpage.start()

if __name__ == '__main__':
    main()
