import aiohttp
import filetype
from maubot import Plugin, MessageEvent
from maubot.handlers import command
from mautrix.types import MediaMessageEventContent, MessageType, ImageInfo
from mautrix.util.config import BaseProxyConfig, ConfigUpdateHelper
from typing import Type


class Config(BaseProxyConfig):
  def do_update(self, helper: ConfigUpdateHelper) -> None:
    helper.copy("region")
    helper.copy("safesearch")


class ImageSearchBot(Plugin):
    headers = {
        "Sec-GPC": "1",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "pl,en-US;q=0.7,en;q=0.3",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:139.0) Gecko/20100101 Firefox/139.0",
        "referer": "https://duckduckgo.com/"
    }

    async def start(self) -> None:
        await super().start()
        self.config.load_and_update()

    @command.new(name="i", help="Get the most relevant result from DuckDuckGo Image Search")
    @command.argument("query", pass_raw=True, required=True)
    async def search(self, evt: MessageEvent, query: str) -> None:
        await evt.mark_read()
        query = query.strip()
        if not query:
            await evt.respond("Usage: !i <query>")
            return

        url = await self.get_image_url(query)
        if not url:
            await evt.reply(f"Failed to find results for *{query}*")
            return

        content = await self.prepare_message(url)
        if content:
            await evt.reply(content)
        else:
            await evt.reply(f"Failed to download image for *{query}*")

    async def get_image_url(self, query: str) -> str:
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
                    break
                except ValueError:
                    self.log.error(f"Token parsing failed")
                    return ""
        except aiohttp.ClientError as e:
            self.log.error(f"Failed to obtain token. Connection failed: {e}")
            return ""

        # Proceed to get first image URL from the results
        params = {
            "l": self.get_region(),  # region
            "o": "json",  # request json
            "q": query,  # keywords
            "vqd": token,  # DDG search token
            "f": ",,,,,", # ignore other image parameters: timelimit, size, color, type_image, layout, license_image
            "p": self.get_safesearch(),  # safe search
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
            content_type = filetype.guess(data)
            if not content_type:
                self.log.error("Failed to determine file type")
                return None
            # Upload image to Matrix server
            uri = await self.client.upload_media(
                data=data,
                mime_type=content_type.mime,
                filename=f"image.{content_type.extension}",
                size=len(data))
            # Prepare a message with the image
            content = MediaMessageEventContent(
                url=uri,
                body=f"image.{content_type.extension}",
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
        return safesearch_base.get(self.config["safesearch"], safesearch_base["on"])

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
        if self.config["region"] in regions:
            return self.config["region"]
        return "wt-wt"

    @classmethod
    def get_config_class(cls) -> Type[BaseProxyConfig]:
        return Config