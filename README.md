# save_webpage

```
usage: save_webpage.py [-h] [--version] [-q] [--insecure]
                       [--forbidden-urls FORBIDDEN_URLS [FORBIDDEN_URLS ...]]
                       [--follow-links] [-b BASE_URL]
                       [--index-name INDEX_NAME]
                       [--mode {relative,absolute,nochange}]
                       [--config PATH_TO_CONFIG_FILE]
                       [list_of_seed_urls [list_of_seed_urls ...]] output

Save_Webpage Save webpages and all its resources. Apply search and replace of
matched strings.

positional arguments:
  list_of_seed_urls     Seed urls
  output                Output directory

optional arguments:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
  -q, --quite           don't show verbose url get log in stderr
  --insecure            Ignore the certificate
  --forbidden-urls FORBIDDEN_URLS [FORBIDDEN_URLS ...]
                        Forbidden urls
  --follow-links        Follow links
  -b BASE_URL, --base-url BASE_URL
                        Resolves relative links using URL as the point of
                        reference
  --index-name INDEX_NAME
                        Default index file
  --mode {relative,absolute,nochange}
                        Mode of extraction
  --config PATH_TO_CONFIG_FILE
                        Path to configuration file

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
