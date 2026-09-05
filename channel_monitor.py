"""
Telegram Channel Monitor & Album Auto-Publisher (channel_monitor.py)
===================================================================
Features:
1. Album Aggregator: Collects multiple photos with the same grouped_id and posts them as a single Telegram Album.
2. Photo-Only Filter: Ignores text-only posts; only processes posts with photo media.
3. Pure Caption Preservation: Keeps all product specs, model names, and emojis intact.
4. Precise PII Stripper: Cleans only phone numbers, Telegram links, websites, WhatsApp links, and mentions.
5. Multi-Channel Support & 60-Day Catchup.
"""

import os
import re
import json
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from telethon import TelegramClient, events

try:
    from config import (
        TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_SESSION,
        DEFAULT_CHANNELS, BOT_LINK
    )
except ImportError:
    TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID", "0"))
    TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
    TELEGRAM_SESSION = os.getenv("TELEGRAM_SESSION", "aikala_monitor_session")
    DEFAULT_CHANNELS = []
    BOT_LINK = os.getenv("BOT_LINK", "")

from database import Database

TARGET_IMAGE_CHANNEL = "@Aikala_Image"
STATE_FILE = "monitor_state.json"
BACKFILL_DAYS = 60

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | [Monitor] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("ChannelMonitor")
for _n in ("telethon", "httpx", "httpcore", "urllib3"):
    logging.getLogger(_n).setLevel(logging.WARNING)


def clean_caption_preserve_specs(text: str) -> str:
    """
    متن، مشخصات و نام مدل را دقیقاً حفظ کرده و فقط شماره‌ها، لینک‌ها و آیدی‌ها را حذف می‌کند.
    """
    if not text:
        return ""

    lines = text.split("\n")
    cleaned_lines = []

    for line in lines:
        l = line

        # ۱. حذف لینک‌های وبسایت (http, https, www, دامنه های ir, com و...)
        l = re.sub(r'https?://\S+', '', l, flags=re.IGNORECASE)
        l = re.sub(r'www\.\S+', '', l, flags=re.IGNORECASE)
        l = re.sub(r'\b[a-zA-Z0-9.\-_]+\.(?:ir|com|net|org|biz|info|shop|store|online)\b(?:\/\S*)?', '', l, flags=re.IGNORECASE)

        # ۲. حذف لینک‌های تلگرام، واتساپ و اینستاگرام
        l = re.sub(r'(?:t\.me|telegram\.me|telegram\.dog)\/\S+', '', l, flags=re.IGNORECASE)
        l = re.sub(r'(?:wa\.me|api\.whatsapp\.com)\/\S+', '', l, flags=re.IGNORECASE)
        l = re.sub(r'(?:instagram\.com|instagr\.am)\/\S+', '', l, flags=re.IGNORECASE)

        # ۳. حذف آیدی‌های تلگرام (@username)
        l = re.sub(r'@[a-zA-Z0-9_]{3,}', '', l)

        # ۴. حذف شماره تلفن‌های همراه و ثابت با پیش‌شماره‌های مختلف (+98, 09, 08, 02 و...)
        l = re.sub(r'(?:\+?98|0098|0)?9\d{2}[\s\-_.]?\d{3}[\s\-_.]?\d{4}', '', l)
        l = re.sub(r'(?:\+?98|0098|0)\d{2,3}[\s\-_.]?\d{7,8}', '', l)
        l = re.sub(r'\b0\d{10}\b', '', l)

        # ۵. حذف کلمات تماس و مشاوره که بعد از حذف شماره تنها مانده‌اند
        l = re.sub(r'(?:تماس|مشاوره|واتساپ|سفارش|تلفن|همراه|پشتیبانی)\s*:\s*$', '', l, flags=re.IGNORECASE)

        l = l.strip()
        # اگر خط پس از پاکسازی شماره یا لینک خالی شد، اضافه نشود
        if l or (not l and cleaned_lines and cleaned_lines[-1] != ""):
            cleaned_lines.append(l)

    result = "\n".join(cleaned_lines).strip()
    return result


class ChannelMonitor:
    def __init__(self):
        self.client: Optional[TelegramClient] = None
        self.db = Database()
        self.channels: List[Dict[str, Any]] = []
        self.state: Dict[str, Any] = {}
        
        # بافر برای تجمیع آلبوم‌های ورودی زنده
        self.album_buffers: Dict[int, Dict[str, Any]] = {}
        self.album_tasks: Dict[int, asyncio.Task] = {}

    def _load_state(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    self.state = json.load(f)
            except Exception as e:
                logger.warning(f"Could not load state file: {e}")
                self.state = {}

    def _save_state(self, channel_key: str, message_id: int):
        prev_id = self.state.get(channel_key, 0)
        if message_id > prev_id:
            self.state[channel_key] = message_id
            try:
                with open(STATE_FILE, "w", encoding="utf-8") as f:
                    json.dump(self.state, f, indent=2)
            except Exception as e:
                logger.error(f"Could not save state: {e}")

    async def init_client(self):
        self._load_state()
        self.client = TelegramClient(TELEGRAM_SESSION, TELEGRAM_API_ID, TELEGRAM_API_HASH)
        await self.client.start()
        logger.info("✅ Telethon client initialized successfully.")

    async def load_channels(self):
        await self.db.init()
        try:
            db_channels = await self.db.get_monitored_channels()
            if db_channels:
                self.channels = db_channels
                logger.info(f"Loaded {len(self.channels)} channels from database.")
                return
        except Exception as e:
            logger.warning(f"DB load warning: {e}")

        self.channels = list(DEFAULT_CHANNELS) if DEFAULT_CHANNELS else []
        for ch in self.channels:
            try:
                await self.db.add_monitored_channel(ch["channel_id"], ch.get("channel_name", ""))
            except Exception:
                pass
        logger.info(f"Loaded {len(self.channels)} default channels.")

    async def _send_repost(self, media_files: List[Any], caption: str, channel_key: str, max_msg_id: int):
        """ارسال یک تک‌عکس یا یک آلبوم چندتایی کامل به کانال مقصد"""
        # فیلتر کردن فایل‌های خالی یا نامعتبر
        valid_media = [m for m in media_files if m is not None]
        if not valid_media:
            return

        final_text = clean_caption_preserve_specs(caption)
        if BOT_LINK and BOT_LINK not in final_text:
            if final_text:
                final_text = f"{final_text}\n\n🤖 استعلام قیمت لحظه‌ای و سفارش با ضمانت کتبی:\n{BOT_LINK}"
            else:
                final_text = f"🤖 جهت استعلام قیمت و سفارش با ضمانت کتبی:\n{BOT_LINK}"

        try:
            if len(valid_media) == 1:
                await self.client.send_file(
                    TARGET_IMAGE_CHANNEL,
                    file=valid_media[0],
                    caption=final_text
                )
                logger.info(f"🚀 [SINGLE-PHOTO] Reposted to {TARGET_IMAGE_CHANNEL}")
            else:
                await self.client.send_file(
                    TARGET_IMAGE_CHANNEL,
                    file=valid_media,
                    caption=final_text
                )
                logger.info(f"🚀 [ALBUM] Reposted {len(valid_media)} photos as ONE album to {TARGET_IMAGE_CHANNEL}")

            self._save_state(channel_key, max_msg_id)
        except Exception as e:
            logger.error(f"❌ Error reposting to {TARGET_IMAGE_CHANNEL}: {e}")

    async def _flush_album_buffer(self, grouped_id: int):
        """ارسال خودکار آلبوم پس از دریافت تمام قطعات آن از لایو تلگرام"""
        await asyncio.sleep(2.5)  # صبر برای رسیدن تمام عکس‌های آلبوم
        if grouped_id in self.album_buffers:
            data = self.album_buffers.pop(grouped_id)
            self.album_tasks.pop(grouped_id, None)
            await self._send_repost(
                media_files=data["media_list"],
                caption=data["caption"],
                channel_key=data["channel_key"],
                max_msg_id=data["max_msg_id"]
            )

    async def sync_channel_archive(self, ch: Dict[str, Any]):
        """استخراج کامل و نامحدود ۶۰ روز گذشته یا جبران زمان قطعی و ارسال به صورت آلبوم و تک‌عکس"""
        if not ch.get("active", True):
            return

        channel_id = ch.get("channel_id")
        channel_key = str(channel_id).lower()
        last_id = self.state.get(channel_key, 0)

        try:
            entity = await self.client.get_entity(channel_id)
            collected = []
            
            # تعیین بازه زمانی دقیق ۶۰ روز گذشته
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=BACKFILL_DAYS)

            if last_id == 0:
                logger.info(f"⏳ [DEEP BACKFILL] Fetching ALL messages from past {BACKFILL_DAYS} days for {channel_id} (Since: {cutoff_date.strftime('%Y-%m-%d')})...")
                # با limit=None تمام پیام‌ها تا ۶۰ روز گذشته صفحه به صفحه خوانده می‌شوند
                async for msg in self.client.iter_messages(entity, limit=None):
                    if msg.date < cutoff_date:
                        # وقتی به تاریخ قبل از ۶۰ روز رسیدیم، پیمایش متوقف شود
                        break
                    if msg.photo or msg.media:
                        collected.append(msg)
                
                # برای ارسال از قدیمی به جدید مرتب می‌کنیم
                collected.reverse()
                raw_messages = collected
            else:
                logger.info(f"🔄 [CATCHUP] Catching up {channel_id} from ID #{last_id}...")
                async for msg in self.client.iter_messages(entity, min_id=last_id, limit=None, reverse=True):
                    if msg.photo or msg.media:
                        collected.append(msg)
                raw_messages = collected

            if not raw_messages:
                logger.info(f"✨ {channel_id} is already up to date.")
                return

            logger.info(f"📥 Downloaded {len(raw_messages)} raw media messages from {channel_id}. Now grouping into albums...")

            # گروه‌بندی پیام‌ها بر اساس آلبوم (grouped_id) یا تک‌عکس
            grouped_posts: List[Dict[str, Any]] = []
            curr_group_id = None
            curr_group_media = []
            curr_group_caption = ""
            curr_max_id = 0

            for msg in raw_messages:
                if not msg.photo and not msg.media:
                    continue

                gid = msg.grouped_id
                cap = msg.text or msg.message or ""

                if gid:
                    if gid == curr_group_id:
                        curr_group_media.append(msg.media)
                        if cap and not curr_group_caption:
                            curr_group_caption = cap
                        curr_max_id = max(curr_max_id, msg.id)
                    else:
                        if curr_group_media:
                            grouped_posts.append({
                                "media": curr_group_media,
                                "caption": curr_group_caption,
                                "max_id": curr_max_id
                            })
                        curr_group_id = gid
                        curr_group_media = [msg.media]
                        curr_group_caption = cap
                        curr_max_id = msg.id
                else:
                    if curr_group_media:
                        grouped_posts.append({
                            "media": curr_group_media,
                            "caption": curr_group_caption,
                            "max_id": curr_max_id
                        })
                        curr_group_id = None
                        curr_group_media = []
                        curr_group_caption = ""

                    grouped_posts.append({
                        "media": [msg.media],
                        "caption": cap,
                        "max_id": msg.id
                    })

            if curr_group_media:
                grouped_posts.append({
                    "media": curr_group_media,
                    "caption": curr_group_caption,
                    "max_id": curr_max_id
                })

            total = len(grouped_posts)
            logger.info(f"📦 Found {total} total albums/single posts to publish for {channel_id}.")

            for idx, item in enumerate(grouped_posts, 1):
                await self._send_repost(
                    media_files=item["media"],
                    caption=item["caption"],
                    channel_key=channel_key,
                    max_msg_id=item["max_id"]
                )
                logger.info(f"🚀 Progress: [{idx}/{total}] posts published to {TARGET_IMAGE_CHANNEL}")
                await asyncio.sleep(2.5)  # فاصله زمانی مطمئن برای جلوگیری از محدودیت تلگرام (FloodWait)

            logger.info(f"✅ Sync complete for {channel_id}. All {total} posts successfully backfilled.")

        except Exception as e:
            logger.error(f"⚠️ Error during sync for {channel_id}: {e}", exc_info=True)

    async def periodic_refresher(self):
        """بررسی خودکار اضافه شدن کانال جدید توسط ادمین در تلگرام"""
        while True:
            await asyncio.sleep(45)
            try:
                db_channels = await self.db.get_monitored_channels()
                existing = {str(c["channel_id"]).lower() for c in self.channels}
                for ch in db_channels:
                    cid = str(ch["channel_id"]).lower()
                    if cid not in existing and ch.get("active", True):
                        logger.info(f"🆕 New channel added: {ch['channel_id']}. Starting archive sync...")
                        self.channels.append(ch)
                        await self.sync_channel_archive(ch)
            except Exception as e:
                logger.debug(f"Refresher error: {e}")

    async def start(self):
        await self.init_client()
        await self.load_channels()

        # ۱. استخراج تاریخچه یا جبران زمان قطعی به صورت آلبومی
        for ch in self.channels:
            await self.sync_channel_archive(ch)

        # ۲. فعال‌سازی تسک بررسی کانال‌های جدید
        asyncio.create_task(self.periodic_refresher())

        # ۳. لیسنر زنده هوشمند برای دریافت تک‌عکس‌ها و آلبوم‌های لحظه‌ای
        @self.client.on(events.NewMessage)
        async def live_handler(event):
            msg = event.message
            if not msg or (not msg.photo and not msg.media):
                return  # رد کردن پست‌های متنی بدون عکس

            chat_id = str(event.chat_id)
            username = f"@{event.chat.username}" if hasattr(event.chat, 'username') and event.chat.username else ""

            matched_ch = None
            for ch in self.channels:
                cid = str(ch.get("channel_id", "")).strip().lower()
                if cid in (chat_id.lower(), username.lower()) and ch.get("active", True):
                    matched_ch = ch
                    break

            if not matched_ch:
                return

            channel_key = str(matched_ch.get("channel_id", "")).lower()
            caption = msg.text or msg.message or ""
            gid = msg.grouped_id

            if gid:
                # مدیریت آلبوم چندتایی در حالت زنده
                if gid not in self.album_buffers:
                    self.album_buffers[gid] = {
                        "media_list": [msg.media],
                        "caption": caption,
                        "channel_key": channel_key,
                        "max_msg_id": msg.id
                    }
                else:
                    self.album_buffers[gid]["media_list"].append(msg.media)
                    if caption and not self.album_buffers[gid]["caption"]:
                        self.album_buffers[gid]["caption"] = caption
                    self.album_buffers[gid]["max_msg_id"] = max(self.album_buffers[gid]["max_msg_id"], msg.id)

                # ریست تایمر بافر برای دریافت تمام عکس‌های آلبوم
                if gid in self.album_tasks:
                    self.album_tasks[gid].cancel()
                self.album_tasks[gid] = asyncio.create_task(self._flush_album_buffer(gid))

            else:
                # ارسال تک‌عکس
                await self._send_repost(
                    media_files=[msg.media],
                    caption=caption,
                    channel_key=channel_key,
                    max_msg_id=msg.id
                )

        logger.info("📡 Multi-Channel Album Monitor is actively listening...")
        await self.client.run_until_disconnected()


async def main():
    monitor = ChannelMonitor()
    await monitor.start()

if __name__ == "__main__":
    asyncio.run(main())
