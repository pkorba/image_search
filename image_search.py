import aiohttp
import mimetypes
from maubot import Plugin, MessageEvent
from maubot.handlers import command
from mautrix.types import MediaMessageEventContent, MessageType, ImageInfo


class ImageSearchBot(Plugin):
    headers = {
        "Sec-GPC": "1",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "pl,en-US;q=0.7,en;q=0.3",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:139.0) Gecko/20100101 Firefox/139.0",
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "referer": "https://duckduckgo.com/"
    }

    @command.new(name="i", help="Get the most relevant result from DuckDuckGo Image Search")
    @command.argument("query", pass_raw=True, required=True)
    async def search(self, evt: MessageEvent, query: str) -> None:
        await evt.mark_read()
        query = query.strip()
        if not query:
            await evt.respond("Usage: !i <query>")
            return

        url = await self.image_search(query)
        if not url:
            await evt.reply(f"Failed to find results for *{query}*")
            return

        content = await self.prepare_message(url)
        if content:
            await evt.reply(content)
        else:
            await evt.reply(f"Failed to download image for *{query}*")

    async def image_search(self, query: str) -> str:
        url = "https://duckduckgo.com/"

        # First make a request to above URL, and parse out the 'vqd'
        # This is a special token, which should be used in the subsequent request
        self.log.info("Hitting DuckDuckGo for token")
        params = {
            'q': query
        }
        timeout = aiohttp.ClientTimeout(total=20)
        try:
            response = await self.http.post(url, data=params, timeout=timeout, raise_for_status=True)
            res_text = await response.text()
            for c1, c1_len, c2 in (("vqd=\"", 5, "\""), ("vqd=", 4, "&"), ("vqd='", 5, "'")):
                try:
                    start = res_text.index(c1) + c1_len
                    end = res_text.index(c2, start)
                    token = res_text[start:end]
                    break
                except ValueError:
                    self.log.error(f"Token parsing failed")
                    return ""
        except aiohttp.ClientError as e:
            self.log.error(f"Failed to obtain token. Connection failed: {e}")
            return ""

        # Proceed to get first image URL from the results
        params = {
            "l": "wt-wt",  # region: wt-wt, us-en, uk-en, ru-ru; "wt-wt" - no region
            "o": "json",  # request json
            "q": query,  # keywords
            "vqd": token,  # DDG search token
            "f": ",,,,,", # ignore other image parameters: timelimit, size, color, type_image, layout, license_image
            "p": "1",  # safe search (1 moderate, -1 off)
            "1": "-1"  # ads off
        }
        url += "i.js"
        try:
            response = await self.http.get(url, headers=ImageSearchBot.headers, timeout=timeout, params=params, raise_for_status=True)
            data = await response.json(content_type=None)
            return data["results"][0]["image"] if data["results"] else ""
        except aiohttp.ClientError as e:
            self.log.error(f"Connection failed: {e}")
        return ""

    async def prepare_message(self, url: str) -> MediaMessageEventContent | None:
        try:
            # Download image from external source
            response = await self.http.get(url, headers=ImageSearchBot.headers, raise_for_status=True)
            data = await response.read()
            content_type = response.content_type
            extension = mimetypes.guess_extension(content_type)
            # Upload image to Matrix server
            uri = await self.client.upload_media(
                data=data,
                mime_type=content_type,
                filename=f"image{extension}",
                size=len(data))
            # Prepare a message with the image
            content = MediaMessageEventContent(
                url=uri,
                body=f"image{extension}",
                filename=f"image{extension}",
                msgtype=MessageType.IMAGE,
                external_url=url,
                info=ImageInfo(
                    mimetype=content_type,
                    size=len(data)
                ))
            return content
        except aiohttp.ClientError as e:
            self.log.error(f"Downloading image: Connection failed: {e}")
        except Exception as e:
            self.log.error(f"Uploading image to Matrix server: Unknown error: {e}")
        return None
