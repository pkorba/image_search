import aiohttp
import re
import mimetypes
from maubot import Plugin, MessageEvent
from maubot.handlers import command
from mautrix.types import MediaMessageEventContent, MessageType, ImageInfo


class ImageSearchBot(Plugin):
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
        params = {
            'q': query
        }

        # First make a request to above URL, and parse out the 'vqd'
        # This is a special token, which should be used in the subsequent request
        self.log.info("Hitting DuckDuckGo for token")
        timeout = aiohttp.ClientTimeout(total=20)
        try:
            response = await self.http.post(url, data=params, timeout=timeout, raise_for_status=True)
            res_text = await response.text()
            search_obj = re.search(r"vqd=([\d-]+)&", res_text, re.M | re.I)
        except aiohttp.ClientError as e:
            self.log.error(f"Failed to obtain token. Connection failed: {e}")
            return ""

        if not search_obj:
            self.log.error("Token parsing failed")
            return ""

        headers = {
            "Sec-GPC": "1",
            "accept-encoding": "gzip, deflate, zstd, br",
            "x-requested-with": "XMLHttpRequest",
            "accept-language": "pl,en-US;q=0.7,en;q=0.3",
            "user-agent": "Mozilla/5.0 (X11; Linux x86_64; rv:138.0) Gecko/20100101 Firefox/138.0",
            "accept": "application/json, text/javascript, */*; q=0.01",
            "referer": "https://duckduckgo.com/",
            "authority": "duckduckgo.com"
        }

        params = (
            ("l", "wt-wt"),
            ("o", "json"),
            ("q", query),
            ("vqd", search_obj.group(1)),
            ("f", ",,,"),
            ("p", "2")
        )

        request_url = url + "i.js"
        try:
            response = await self.http.get(request_url, headers=headers, timeout=timeout, params=params, raise_for_status=True)
            data = await response.json(content_type=None)
            return data["results"][0]["image"] if data["results"] else ""
        except aiohttp.ClientError as e:
            self.log.error(f"Connection failed: {e}")
        return ""

    async def prepare_message(self, url: str) -> MediaMessageEventContent | None:
        try:
            response = await self.http.get(url, raise_for_status=True)
            data = await response.read()
            content_type = response.content_type
            extension = mimetypes.guess_extension(content_type)
            uri = await self.client.upload_media(
                data=data,
                mime_type=content_type,
                filename=f"image{extension}",
                size=len(data))

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
            self.log.error(f"Uploading image to Matrix server: Connection failed: {e}")
        except Exception as e:
            self.log.error(f"Uploading image to Matrix server: Unknown error: {e}")
        return None
