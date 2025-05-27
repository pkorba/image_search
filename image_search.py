import aiohttp
import re
import mimetypes
from maubot import Plugin, MessageEvent
from maubot.handlers import command
from mautrix.types import MediaMessageEventContent, MessageType, ImageInfo


class ImageSearchBot(Plugin):
    @command.new(name="i", help="DuckDuckGo Image Search")
    @command.argument("query", pass_raw=True, required=True)
    async def search(self, evt: MessageEvent, query: str) -> None:
        await evt.mark_read()
        query = query.strip()
        if not query:
            await evt.respond("Usage: !i <query>")
            return
        url = await self.image_search(query)
        if not url:
            await evt.reply(f"Failed to find results for {query}")
            return
        try:
            resp = await self.http.get(url)
            if resp.status == 200:
                data = await resp.read()
                content_type = resp.content_type
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
                await evt.reply(content)
            else:
                await evt.reply(f"Failed to download image for {query}")
        except aiohttp.ClientError as e:
            self.log.error(f"Connection failed: {url}: {e}")
        except Exception as e:
            self.log.error(f"Unknown error: {url}: {e}")

    async def image_search(self, query: str) -> str:
        url = "https://duckduckgo.com/"
        params = {
            'q': query
        }

        # First make a request to above URL, and parse out the 'vqd'
        # This is a special token, which should be used in the subsequent request
        self.log.info("Hitting DuckDuckGo for Token")
        search_obj = ""
        timeout = aiohttp.ClientTimeout(total=7)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, data=params) as res:
                    res_text = await res.text()
                    search_obj = re.search(r"vqd=([\d-]+)&", res_text, re.M | re.I)
        except aiohttp.ClientError as e:
            self.log.error(f"Failed to obtain token. Connection failed: {e}")
            return ""

        if not search_obj:
            print("Token Parsing Failed !")
            return ""
        self.log.info("Obtained Token")

        headers = {
            'dnt': '1',
            'accept-encoding': 'gzip, deflate, zstd, br',
            'x-requested-with': 'XMLHttpRequest',
            'accept-language': 'pl,en-US;q=0.8,en;q=0.6,ms;q=0.4',
            'user-agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:138.0) Gecko/20100101 Firefox/138.0',
            'accept': 'application/json, text/javascript, */*; q=0.01',
            'referer': 'https://duckduckgo.com/',
            'authority': 'duckduckgo.com',
        }

        params = (
            ('l', 'wt-wt'),
            ('o', 'json'),
            ('q', query),
            ('vqd', search_obj.group(1)),
            ('f', ',,,'),
            ('p', '2')
        )

        request_url = url + "i.js"
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.get(request_url, params=params) as res:
                    data = await res.json(content_type=None)
                    return data["results"][0]["image"] if data["results"] else ""
        except aiohttp.ClientError as e:
            self.log.error(f"Failed to find results for {query}. Connection failed: {e}")
            return ""
