import aiohttp
import filetype
from maubot import Plugin, MessageEvent
from maubot.handlers import command
from mautrix.types import MediaMessageEventContent, MessageType, ImageInfo, Format
from mautrix.util.config import BaseProxyConfig, ConfigUpdateHelper
from typing import Type


class Config(BaseProxyConfig):
    def do_update(self, helper: ConfigUpdateHelper) -> None:
        helper.copy("region")
        helper.copy("safesearch")


class ImageSearchBot(Plugin):
    retry_count = 3

    async def start(self) -> None:
        await super().start()
        self.config.load_and_update()

    @command.new(name="i", help="Get the most relevant result from DuckDuckGo Image Search")
    @command.argument("query", pass_raw=True, required=True)
    async def search(self, evt: MessageEvent, query: str) -> None:
        await evt.mark_read()
        query = query.strip()
        if not query:
            await evt.reply("Usage: !i <query>")
            return
        query = "-instagram.com -facebook.com -fbsbx.com " + query
        if len(query) > 499:
            await evt.reply("Query is too long.")

        urls = await self.get_image_url(query)
        if not urls:
            await evt.reply(f"Failed to find results for *{query}*")
            return
        for i in range (0, self.retry_count):
            content = await self.prepare_message(urls[i])
            if content:
                await evt.reply(content)
            return
        await evt.reply(f"Failed to download image for *{query}*")

    async def get_image_url(self, query: str) -> list[str]:
        vqd = await self.get_vqd(query)
        if not vqd:
            return []
        # Proceed to get first image URL from the results
        params = {
            "l": self.get_region(),  # region
            "o": "json",  # request json
            "q": query,  # keywords
            "vqd": vqd,  # DDG search token
            "f": ",,,,,",  # ignore other image parameters: timelimit, size, color, type_image, layout, license_image
            "p": self.get_safesearch(),  # safe search
            "1": "-1"  # ads off
        }
        headers = {
            "referer": "https://duckduckgo.com/",
            'X-Requested-With': 'XMLHttpRequest'
        }
        url = "https://duckduckgo.com/i.js"
        timeout = aiohttp.ClientTimeout(total=20)
        results = []
        try:
            response = await self.http.get(url, headers=headers, timeout=timeout, params=params, raise_for_status=True)
            data = await response.json(content_type=None)
            if data.get("results", None):
                end = self.retry_count if len(data["results"]) >= self.retry_count else len(data["results"])
                for i in range(0, end):
                    results.append(data["results"][i]["image"])
        except aiohttp.ClientError as e:
            self.log.error(f"Connection failed: {e}")
        return []

    async def get_vqd(self, query: str) -> str:
        url = "https://duckduckgo.com/"

        # First make a request to above URL, and parse out the 'vqd'
        # This is a special token, which should be used in the subsequent request
        self.log.debug("Hitting DuckDuckGo for token")
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
                    return token
                except ValueError:
                    self.log.error(f"Token parsing failed")
                    return ""
        except aiohttp.ClientError as e:
            self.log.error(f"Failed to obtain token. Connection failed: {e}")
            return ""

    async def prepare_message(self, url: str) -> MediaMessageEventContent | None:
        headers = {
            "Sec-GPC": "1",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "en,en-US;q=0.5",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:139.0) Gecko/20100101 Firefox/139.0"
        }

        try:
            # Download image from external source
            response = await self.http.get(url, headers=headers, raise_for_status=True)
            data = await response.read()
            content_type = filetype.guess(data)
            if not content_type:
                self.log.error("Failed to determine file type")
                return None
            if content_type not in filetype.image_matchers:
                self.log.error("Downloaded file is not an image")
                return None
            # Upload image to Matrix server
            uri = await self.client.upload_media(
                data=data,
                mime_type=content_type.mime,
                filename=f"image.{content_type.extension}",
                size=len(data))
            # Prepare a message with the image
            html = (
                "<blockquote>"
                "<b><sub>Results from DuckDuckGo</sub></b>"
                "</blockquote>"
            )
            content = MediaMessageEventContent(
                url=uri,
                body=f"> **Results from DuckDuckGo**",
                format=Format.HTML,
                formatted_body=html,
                filename=f"image.{content_type.extension}",
                msgtype=MessageType.IMAGE,
                external_url=url,
                info=ImageInfo(
                    mimetype=content_type.mime,
                    size=len(data)
                ))
            return content
        except aiohttp.ClientError as e:
            self.log.error(f"Downloading image: Connection failed: {e}")
        except Exception as e:
            self.log.error(f"Uploading image to Matrix server: Unknown error: {e}")
        return None

    def get_safesearch(self) -> str:
        safesearch_base = {
            "on": "1",
            "off": "-1"
        }
        return safesearch_base.get(self.config.get("safesearch", "on"), safesearch_base["on"])

    def get_region(self) -> str:
        regions = [
            "xa-ar",  # Arabia
            "xa-en",  # Arabia (en)
            "ar-es",  # Argentina
            "au-en",  # Australia
            "at-de",  # Austria
            "be-fr",  # Belgium (fr)
            "be-nl",  # Belgium (nl)
            "br-pt",  # Brazil
            "bg-bg",  # Bulgaria
            "ca-en",  # Canada
            "ca-fr",  # Canada (fr)
            "ct-ca",  # Catalan
            "cl-es",  # Chile
            "cn-zh",  # China
            "co-es",  # Colombia
            "hr-hr",  # Croatia
            "cz-cs",  # Czech Republic
            "dk-da",  # Denmark
            "ee-et",  # Estonia
            "fi-fi",  # Finland
            "fr-fr",  # France
            "de-de",  # Germany
            "gr-el",  # Greece
            "hk-tzh",  # Hong Kong
            "hu-hu",  # Hungary
            "in-en",  # India
            "id-id",  # Indonesia
            "id-en",  # Indonesia (en)
            "ie-en",  # Ireland
            "il-he",  # Israel
            "it-it",  # Italy
            "jp-jp",  # Japan
            "kr-kr",  # Korea
            "lv-lv",  # Latvia
            "lt-lt",  # Lithuania
            "xl-es",  # Latin America
            "my-ms",  # Malaysia
            "my-en",  # Malaysia (en)
            "mx-es",  # Mexico
            "nl-nl",  # Netherlands
            "nz-en",  # New Zealand
            "no-no",  # Norway
            "pe-es",  # Peru
            "ph-en",  # Philippines
            "ph-tl",  # Philippines (tl)
            "pl-pl",  # Poland
            "pt-pt",  # Portugal
            "ro-ro",  # Romania
            "ru-ru",  # Russia
            "sg-en",  # Singapore
            "sk-sk",  # Slovak Republic
            "sl-sl",  # Slovenia
            "za-en",  # South Africa
            "es-es",  # Spain
            "se-sv",  # Sweden
            "ch-de",  # Switzerland (de)
            "ch-fr",  # Switzerland (fr)
            "ch-it",  # Switzerland (it)
            "tw-tzh",  # Taiwan
            "th-th",  # Thailand
            "tr-tr",  # Turkey
            "ua-uk",  # Ukraine
            "uk-en",  # United Kingdom
            "us-en",  # United States
            "ue-es",  # United States (es)
            "ve-es",  # Venezuela
            "vn-vi",  # Vietnam
            "wt-wt",  # No region
        ]
        region = self.config.get("region", "wt-wt")
        if region in regions:
            return self.config["region"]
        return "wt-wt"

    @classmethod
    def get_config_class(cls) -> Type[BaseProxyConfig]:
        return Config
