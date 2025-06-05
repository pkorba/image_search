# Image Search Bot

A maubot for Matrix messaging that performs an image search on user's behalf using DuckDuckGo and uploads the best matching result as a response to the user's message.

![bot_image_search](https://github.com/user-attachments/assets/e8d8b98d-9dc9-4480-8eff-a9714e8a6697)


## Usage
Type the query you'd want to pass to the search engine.
```
[p]i query
```

## Configuration

In configuration you can choose the following options:  
* `region` - available options are the ones listed in [DuckDuckGo help page](https://duckduckgo.com/duckduckgo-help-pages/settings/params). Defaults to `wt-wt` (no region).
* `safesearch` - available options are `on` and `off`. Controls safe search filter. Defaults to `on`.
