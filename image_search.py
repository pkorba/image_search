import asyncio
import aiohttp
import filetype
from maubot import Plugin, MessageEvent
from maubot.handlers import command
from mautrix.types import MediaMessageEventContent, MessageType, ImageInfo, Format
from mautrix.util.config import BaseProxyConfig, ConfigUpdateHelper
from typing import Type


class Config(BaseProxyConfig):
    def do_update(self, helper: ConfigUpdateHelper) -> None:
        helper.copy("ddg_region")
        helper.copy("ddg_safesearch")
        helper.copy("searxng")
        helper.copy("searxng_url")
        helper.copy("searxng_port")
        helper.copy("searxng_language")
        helper.copy("searxng_safesearch")
        helper.copy("blacklist")


class ImageData:
    def __init__(self, url: str, width: int, height: int, engine: str) -> None:
        self.url = url
        self.width = width
        self.height = height
        self.engine = engine


class ImageSearchBot(Plugin):
    retry_count = 3
    blacklist: list[str] = []
    headers = {
        "Sec-GPC": "1",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "en,en-US;q=0.5",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:139.0) Gecko/20100101 Firefox/139.0",
    }

    async def start(self) -> None:
        await super().start()
        self.config.load_and_update()
        self.blacklist = list(self.config["blacklist"]) if self.config.get("blacklist", None) else []
        self.log.info(f"Using {'SearXNG' if self.get_sx() else 'DuckDuckGo'} backend.")

    @command.new(name="i", aliases=["image"], help="Search for an image in DuckDuckGo or SearXNG")
    @command.argument("query", pass_raw=True, required=True)
    async def search(self, evt: MessageEvent, query: str) -> None:
        await evt.mark_read()
        # Remove characters that result in search engine redirecting to external domain
        bang = "!!" if self.get_sx() else "!"
        query = query.strip().replace(bang, "").replace("\\", "")
        if not query:
            await evt.reply("> **Usage:**  \n"
                            "> !i <query>  \n"
                            "> !image <query>")
            return
        # Duckduckgo doesn't accept queries longer than 500 characters
        if len(query) >= 500:
            await evt.reply("> Query is too long.")

        urls = await self.get_image_data(query)
        if not urls:
            await evt.reply(f"> Failed to find results for *{query}*")
            return
        for url in urls:
            content = await self.prepare_message(url)
            if content:
                await evt.reply(content)
                return
        await evt.reply(f"> Failed to download image for *{query}*")

    async def get_image_data(self, query: str) -> list[ImageData]:
        """
        Get list of image data objects
        :param query: search query
        :return: list of image data objects
        """
        if self.get_sx():
            return await self.get_image_data_sx(query)
        return await self.get_image_data_ddg(query)

    async def get_image_data_ddg(self, query: str) -> list[ImageData]:
        """
        Get list of image data objects from DuckDuckGo Image Search
        :param query: search query
        :return: list of image data objects
        """
        vqd = await self.get_vqd(query)
        if not vqd:
            return []
        # Proceed to get first image URL from the results
        params = {
            "q": query,  # keywords
            "vqd": vqd,  # DDG search token
            "l": self.get_ddg_region(),  # region
            "o": "json",  # request json
            "f": ",,,,,",  # ignore other image parameters: timelimit, size, color, type_image, layout, license_image
            "p": self.get_ddg_safesearch(),  # safe search
            "1": "-1"  # ads off
        }
        headers = self.headers.copy()
        headers["referer"] = "https://duckduckgo.com/"
        headers["X-Requested-With"] = "XMLHttpRequest"
        url = "https://duckduckgo.com/i.js"
        results: list[ImageData] = []
        timeout = aiohttp.ClientTimeout(total=20)
        try:
            response = await self.http.get(url, headers=headers, timeout=timeout, params=params, raise_for_status=True)
            data = await response.json(content_type=None)
            if data and data.get("results", None):
                results_filtered = [result for result in data["results"] if result.get("image", "") and not self.in_string(self.blacklist, result["image"])]
                end = min(self.retry_count, len(results_filtered))
                for i in range(0, end):
                    image_result = ImageData(
                        url=results_filtered[i]["image"],
                        width=results_filtered[i].get("width", None),
                        height=results_filtered[i].get("height", None),
                        engine="DuckDuckGo"
                    )
                    results.append(image_result)
        except aiohttp.ClientError as e:
            self.log.error(f"Connection failed: {e}")
        return results

    @staticmethod
    def in_string(substrings: list[str], string: str) -> bool:
        """
        Check if any of strings in the list is a substring of the given string.
        :param substrings: list of substrings
        :param string: string to compare against
        :return: True if substring is in the given string else False
        """
        for substring in substrings:
            if substring in string:
                return True
        return False

    async def get_vqd(self, query: str) -> str:
        """
        Get special search token required by DuckDuckGo.
        :param query: search query
        :return: search token
        """
        url = "https://duckduckgo.com/"
        # Make a request to above URL, and parse out the 'vqd'
        # This is a special token, which should be used in the subsequent request
        params = {
            'q': query
        }
        timeout = aiohttp.ClientTimeout(total=20)
        try:
            response = await self.http.get(url, params=params, timeout=timeout, raise_for_status=True)
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

    async def get_image_data_sx(self, query: str) -> list[ImageData]:
        """
        Get list of image data objects from SearXNG Image Search
        :param query: search query
        :return: list of image data objects
        """
        params = {
            "q": query,  # keywords
            "categories": "images",  # perform image search
            "language": self.get_sx_language(),  # language
            "format": "json",  # request json
            "safesearch": self.get_sx_safesearch(),  # safe search
        }
        url = self.get_sx_address()
        results: list[ImageData] = []
        timeout = aiohttp.ClientTimeout(total=20)
        try:
            response = await self.http.get(url, timeout=timeout, params=params, raise_for_status=True)
            data = await response.json()
        except aiohttp.ClientError as e:
            self.log.error(f"Connection failed: {e}")
            return []

        if data and data.get("results", None):
            results_filtered = [result for result in data["results"] if result.get("img_src", "") and not self.in_string(self.blacklist, result["img_src"])]
            end = min(self.retry_count, len(results_filtered))
            for i in range(0, end):
                if results_filtered[i]["img_src"].startswith("//"):
                    # Some urls in results are missing protocol (e.g. imgur)
                    results_filtered[i]["img_src"] = results_filtered[i]["img_src"].replace("//", "https://")
                resolution = results_filtered[i].get("resolution", "").split("×")
                if len(resolution) == 2:
                    width = int(resolution[0])
                    height = int(resolution[1])
                else:
                    width = None
                    height = None
                engine = results_filtered[i].get("engine", "").replace(".", " ")
                image_result = ImageData(
                    url=results_filtered[i]["img_src"],
                    width=width,
                    height=height,
                    engine=f"SearXNG ({'DuckDuckGo' if engine == 'duckduckgo' else engine.title()})"
                )
                results.append(image_result)
        return results

    async def prepare_message(self, image_data: ImageData) -> MediaMessageEventContent | None:
        """
        Prepare a message by downloading an image from external source, uploading it to Matrix, and creating media message event content
        :param image_data: object representing image data
        :return: content of media message event
        """
        try:
            # Download image from external source
            response = await self.http.get(image_data.url, headers=self.headers, raise_for_status=True)
            data = await response.read()
            content_type = await asyncio.get_event_loop().run_in_executor(None, filetype.guess, data)
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
                f"<blockquote>"
                f"<b><sub>Results from {image_data.engine}</sub></b>"
                f"</blockquote>"
            )
            return MediaMessageEventContent(
                url=uri,
                body=f"> **Results from {image_data.engine}**",
                format=Format.HTML,
                formatted_body=html,
                filename=f"image.{content_type.extension}",
                msgtype=MessageType.IMAGE,
                external_url=image_data.url,
                info=ImageInfo(
                    mimetype=content_type.mime,
                    size=len(data),
                    width=image_data.width,
                    height=image_data.height
                ))
        except aiohttp.ClientError as e:
            self.log.error(f"Downloading image - connection failed: {e}")
        except Exception as e:
            self.log.error(f"Uploading image to Matrix server - unknown error: {e}")
        return None

    def get_ddg_safesearch(self) -> str:
        """
        Get safe search filter status from config for DuckDuckGo Image Search
        :return: Value corresponding to safe search status
        """
        safesearch_base = {
            "on": "1",
            "off": "-1"
        }
        return safesearch_base.get(self.config.get("ddg_safesearch", "on"), safesearch_base["on"])

    def get_sx(self) -> bool:
        """
        Get SearXNG backend status
        :return: SearXNG backend status
        """
        sx_base = {
            "on": True,
            "off": False
        }
        return sx_base.get(self.config.get("searxng", "off"), sx_base["off"])

    def get_sx_address(self) -> str:
        """
        Get SearXNG backend address
        :return: SearXNG backend address
        """
        url = self.config.get("searxng_url", "http://127.0.0.1")
        port = self.config.get("searxng_port", 8080)
        return f"{url}:{port}/search"

    def get_sx_safesearch(self) -> str:
        """
        Get safe search filter status from config for SearXNG Image Search
        :return: Value corresponding to safe search status
        """
        safesearch_base = {
            "on": "2",
            "moderate": "1",
            "off": "0"
        }
        return safesearch_base.get(self.config.get("searxng_safesearch", "moderate"), safesearch_base["moderate"])

    def get_ddg_region(self) -> str:
        """
        Get search region from config for DuckDuckGo Image Search
        :return: Search region
        """
        # https://duckduckgo.com/duckduckgo-help-pages/settings/params
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
        region = self.config.get("ddg_region", "wt-wt").lower()
        if region in regions:
            return region
        return "wt-wt"

    def get_sx_language(self) -> str:
        """
        Get search region from config for SearXNG Image Search
        :return: Search region
        """
        # https://github.com/searxng/searxng/blob/master/searx/sxng_locales.py
        languages = [
            "af",  # Afrikaans
            "ar",  # Arabic
            "ar-SA",  # Arabic
            "be",  # Belarusian
            "bg",  # Bulgarian
            "bg-BG",  # Bulgarian
            "ca",  # Catalan
            "cs",  # Czech
            "cs-CZ",  # Czech
            "cy",  # Welsh
            "da",  # Danish
            "da-DK",  # Danish
            "de",  # German
            "de-AT",  # German
            "de-BE",  # German
            "de-CH",  # German
            "de-DE",  # German
            "el",  # Greek
            "el-GR",  # Greek
            "en",  # English
            "en-AU",  # English
            "en-CA",  # English
            "en-GB",  # English
            "en-IE",  # English
            "en-IN",  # English
            "en-NZ",  # English
            "en-PH",  # English
            "en-PK",  # English
            "en-SG",  # English
            "en-US",  # English
            "en-ZA",  # English
            "es",  # Spanish
            "es-AR",  # Spanish
            "es-CL",  # Spanish
            "es-CO",  # Spanish
            "es-ES",  # Spanish
            "es-MX",  # Spanish
            "es-PE",  # Spanish
            "et",  # Estonian
            "et-EE",  # Estonian
            "eu",  # Basque
            "fa",  # Persian
            "fi",  # Finnish
            "fi-FI",  # Finnish
            "fr",  # French
            "fr-BE",  # French
            "fr-CA",  # French
            "fr-CH",  # French
            "fr-FR",  # French
            "ga",  # Irish
            "gd",  # Scottish Gaelic
            "gl",  # Galician
            "he",  # Hebrew
            "hi",  # Hindi
            "hr",  # Croatian
            "hu",  # Hungarian
            "hu-HU",  # Hungarian
            "id",  # Indonesian
            "id-ID",  # Indonesian
            "is",  # Icelandic
            "it",  # Italian
            "it-CH",  # Italian
            "it-IT",  # Italian
            "ja",  # Japanese
            "ja-JP",  # Japanese
            "kn",  # Kannada
            "ko",  # Korean
            "ko-KR",  # Korean
            "lt",  # Lithuanian
            "lv",  # Latvian
            "ml",  # Malayalam
            "mr",  # Marathi
            "nb",  # Norwegian Bokmål
            "nb-NO",  # Norwegian Bokmål
            "nl",  # Dutch
            "nl-BE",  # Dutch
            "nl-NL",  # Dutch
            "pl",  # Polish
            "pl-PL",  # Polish
            "pt",  # Portuguese
            "pt-BR",  # Portuguese
            "pt-PT",  # Portuguese
            "ro",  # Romanian
            "ro-RO",  # Romanian
            "ru",  # Russian
            "ru-RU",  # Russian
            "sk",  # Slovak
            "sl",  # Slovenian
            "sq",  # Albanian
            "sv",  # Swedish
            "sv-SE",  # Swedish
            "ta",  # Tamil
            "te",  # Telugu
            "th",  # Thai
            "th-TH",  # Thai
            "tr",  # Turkish
            "tr-TR",  # Turkish
            "uk",  # Ukrainian
            "ur",  # Urdu
            "vi",  # Vietnamese
            "vi-VN",  # Vietnamese
            "zh",  # Chinese
            "zh-CN",  # Chinese
            "zh-HK",  # Chinese
            "zh-TW",  # Chinese
            "all"  # All languages
        ]
        lang = self.config.get("searxng_language", "all")
        if lang in languages:
            return lang
        return "all"

    @classmethod
    def get_config_class(cls) -> Type[BaseProxyConfig]:
        return Config
