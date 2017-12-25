# save_webpage

```
usage: save_webpage.py [-h] [--version] [-q] [--insecure] [-i URL_LIST]
                       [-o OUTPUT]
                       [--javascript-replacements JAVASCRIPT_REPLACEMENTS]
                       [--html-replacements HTML_REPLACEMENTS] [-b BASE_URL]
                       [url]

SAVE_WEBPAGE Save a webpage and all its resource.

positional arguments:
  url                   the website to store

optional arguments:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
  -q, --quite           don't show verbose url get log in stderr
  --insecure            Ignore the certificate
  -i URL_LIST, --url-list URL_LIST
                        Path to file containing list of url's
  -o OUTPUT, --output OUTPUT
                        Output directory
  --javascript-replacements JAVASCRIPT_REPLACEMENTS
                        Path to file containing javascript replacements in
                        JSON format
  --html-replacements HTML_REPLACEMENTS
                        Path to file containing html replacements in JSON
                        format
  -b BASE_URL, --base-url BASE_URL
                        Resolves relative links using URL as the point of
                        reference

save_webpage.py: Takes a url and extracts that website with all its internal
resource files. Transforms all internal resources so that they link to local
files. Process css files exctracting new resource and converting url's.
Possibility to replace javascript and html files using custom substitutions.
Full Unicode/UTF-8 support.
```

# Command-line usage:

Examples:

```
$ python save_webpage.py -h
    you are reading this help message

$ python save_webpage.py http://www.google.com
    save google url page for offline reading, keep style untainted
    the website and all its resource are saved in the 'output' folder

$ python save_webpage.py http://gabrielecirulli.github.io/2048/ --output game
    save dynamic page with Javascript example
    the 2048 game can be played offline after being saved
    the website and all its resource are saved in the 'game' folder
```
