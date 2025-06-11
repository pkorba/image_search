# Image Search Bot

A maubot for Matrix messaging that performs an image search on user's behalf using [DuckDuckGo](https://duckduckgo.com/) or [SearXNG](https://docs.searxng.org/) instance and uploads the best matching result as a response to the user's message.

![bot_image_search](https://github.com/user-attachments/assets/e8d8b98d-9dc9-4480-8eff-a9714e8a6697)


## Usage
Type the query you'd like to pass to the search engine.
```
[p]i query
[p]image query
```

## Configuration

This bot can fetch results from two sources, DuckDuckGo or a SearXNG instance. By default, it uses DuckDuckGo and doesn't require any changes to configuration to work out of the box.  
The following options affect DuckDuckGo results:  
* `region` - default search language. Available options are the ones listed in [DuckDuckGo help page](https://duckduckgo.com/duckduckgo-help-pages/settings/params). Defaults to `wt-wt` (no region).
* `safesearch` - available options are `on`  (default) and `off`. Controls the safe search filter.

Alternatively, it's posible to use SearXNG instance instead of DuckDuckGo. For that you need to have access to SearXNG instance that offers a public JSON API. The available options are:
* `searxng` - available options are `on` and `off` (default). This option controls whether SearXNG integration is enabled. If it's `on`, DuckDuckGo is automatically disabled.
* `searxng_url` - public URL address of SearXNG instance.
* `searxng_port` - port number for `searxng_url`
* `searxng_language` - default search language. Available options are listed [here](https://github.com/searxng/searxng/blob/master/searx/sxng_locales.py#L12). Defaults to `all`.
* `searxng_safesearch` - available options are `on`, `off`, and `moderate` (default). Controls the safe search filter. Keep in mind that some engines may not support that feature. See if an engine supports safe search in the preferences page of a SearXNG instance.

The only shared option between DuckDuckGo and SearXNG configuration is `blacklist`. It's a list of domains that is excluded from search results. By default, it contains some Meta services because instead serving an image they redirect to full website, which results in errors during download. You can add additional domains you want to exclude.

## Notes

- Initially I wanted to let the user choose what search engines to use by passing `engines` parameter to SearXNG instance and exposing that option in configuration, but in my testing that parameter proved to be broken/unreliable. However, assuming you use your own private SearXNG instance, you can change which search engines are used for generating results in the instance's settings.
- This bot requires SearXNG instance to expose public JSON API. By default, this is disabled in instance's settings. You can change that by adding `json` to `formats` in `search` section of the settings (settings.yml):
```yaml
  # remove format to deny access, use lower case.
  # formats: [html, csv, json, rss]
  formats:
    - html
    - json  # <-- add this line
```


## Disclaimer

This plugin is not affiliated with DuckDuckGo or SearXNG. It is not intended for commercial use or any purpose that violates DuckDuckGo's Terms of Service. By using this plugin, you acknowledge that you will not use it in a way that infringes on DuckDuckGo's terms. The official DuckDuckGo website can be found at https://duckduckgo.com. The official SearXNG website can be found at https://docs.searxng.org/
