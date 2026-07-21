import asyncio
import aiohttp
import json
import os
import re
import time
import random
import logging
import zipfile
import hashlib
from typing import Dict, List, Any, Tuple, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from base64 import b64encode, b64decode

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from pyrogram.errors import FloodWait
from pyromod import listen
from pyromod.exceptions.listener_timeout import ListenerTimeout

from config import api_id, api_hash, bot_token, auth_users

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Thread pool for parallel processing
THREADPOOL = ThreadPoolExecutor(max_workers=100)

# Constants
IMAGE_LIST = [
    "https://graph.org/file/8b1f4146a8d6b43e5b2bc-be490579da043504d5.jpg",
    "https://graph.org/file/b75dab2b3f7eaff612391-282aa53538fd3198d4.jpg",
    "https://graph.org/file/38de0b45dd9144e524a33-0205892dd05593774b.jpg",
    "https://graph.org/file/be39f0eebb9b66d7d6bc9-59af2f46a4a8c510b7.jpg",
    "https://graph.org/file/8b7e3d10e362a2850ba0a-f7c7c46e9f4f50b10b.jpg",
]

# Initialize bot client
bot = Client(
    "bot",
    api_id=api_id,
    api_hash=api_hash,
    bot_token=bot_token
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def format_time(seconds: float) -> str:
    """Format time in seconds to human readable format"""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    
    if minutes == 0:
        if secs < 1:
            return f"{seconds:.2f} seconds"
        return f"{secs} seconds"
    return f"{minutes} minutes {secs} seconds"


def get_auth_user_info() -> Tuple[str, str]:
    """Get auth user info for bot owner"""
    return auth_users[0]


async def check_user_auth(user_id: int, bot, message) -> bool:
    """Check if user is authorized to use the bot"""
    if user_id not in auth_users:
        auth_user = auth_users[0]
        user = await bot.get_users(auth_user)
        owner_username = "@" + user.username
        await bot.send_message(
            message.chat.id,
            f"**You Are Not Subscribed To This Bot\nContact - {owner_username}**"
        )
        return False
    return True


def clean_filename(name: str, max_length: int = 244) -> str:
    """Clean filename by removing invalid characters"""
    return name.replace("/", "-").replace("|", "-")[:max_length]


# =============================================================================
# START COMMAND
# =============================================================================

@bot.on_message(filters.command(["start"]))
async def start_command(bot: Client, message: Message):
    """Handle start command"""
    random_image_url = random.choice(IMAGE_LIST)
    
    keyboard = [
        [InlineKeyboardButton("🚀 Physics Wallah without Purchase 🚀", callback_data="pwwp")],
        [InlineKeyboardButton("📘 Classplus without Purchase 📘", callback_data="cpwp")],
        [InlineKeyboardButton("📒 Appx Without Purchase 📒", callback_data="appxwp")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await message.reply_photo(
        photo=random_image_url,
        caption="**Developer - @erpurchasebot\nPLEASE👇PRESS👇HERE**",
        quote=True,
        reply_markup=reply_markup
    )


# =============================================================================
# PHYSICS WALLAH SECTION
# =============================================================================

class PhysicsWallahDownloader:
    """Class to handle Physics Wallah content downloading"""
    
    BASE_URL = "https://api.penpencil.co"
    HEADERS = {
        'Host': 'api.penpencil.co',
        'client-id': '5eb393ee95fab7468a79d189',
        'client-version': '1910',
        'user-agent': 'Mozilla/5.0 (Linux; Android 12; M2101K6P) AppleWebKit/537.36',
        'randomid': '72012511-256c-4e1c-b4c7-29d67136af37',
        'client-type': 'WEB',
        'content-type': 'application/json; charset=utf-8',
    }
    
    def __init__(self, session: aiohttp.ClientSession, user_id: int):
        self.session = session
        self.user_id = user_id
        
    async def fetch_data(self, url: str, params: Dict = None, data: Dict = None, 
                        method: str = 'GET', max_retries: int = 3) -> Optional[Dict]:
        """Fetch data from API with retry logic"""
        for attempt in range(max_retries):
            try:
                async with self.session.request(
                    method, url, params=params, json=data, headers=self.HEADERS
                ) as response:
                    response.raise_for_status()
                    return await response.json()
            except aiohttp.ClientError as e:
                logger.error(f"Attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
        return None
    
    async def login_with_phone(self, phone: str) -> Optional[str]:
        """Login with phone number and OTP"""
        data = {
            "username": phone,
            "countryCode": "+91",
            "organizationId": "5eb393ee95fab7468a79d189"
        }
        
        try:
            await self.session.post(
                f"{self.BASE_URL}/v1/users/get-otp?smsType=0",
                json=data, headers=self.HEADERS
            )
        except Exception as e:
            raise Exception(f"Failed to send OTP: {e}")
        
        return None  # OTP sent successfully
    
    async def verify_otp(self, phone: str, otp: str) -> str:
        """Verify OTP and get access token"""
        payload = {
            "username": phone,
            "otp": otp,
            "client_id": "system-admin",
            "client_secret": "KjPXuAVfC5xbmgreETNMaL7z",
            "grant_type": "password",
            "organizationId": "5eb393ee95fab7468a79d189"
        }
        
        async with self.session.post(
            f"{self.BASE_URL}/v3/oauth/token",
            json=payload, headers=self.HEADERS
        ) as response:
            data = await response.json()
            return data["data"]["access_token"]
    
    async def get_purchased_batches(self) -> List[Dict]:
        """Get all purchased batches"""
        params = {'mode': '1', 'page': '1'}
        async with self.session.get(
            f"{self.BASE_URL}/v3/batches/all-purchased-batches",
            headers=self.HEADERS, params=params
        ) as response:
            response.raise_for_status()
            return (await response.json()).get("data", [])
    
    async def search_batches(self, name: str) -> List[Dict]:
        """Search for batches by name"""
        url = f"{self.BASE_URL}/v3/batches/search?name={name}"
        data = await self.fetch_data(url)
        return data.get("data", []) if data else []
    
    async def get_batch_details(self, batch_id: str) -> Dict:
        """Get batch details including subjects"""
        url = f"{self.BASE_URL}/v3/batches/{batch_id}/details"
        return await self.fetch_data(url)
    
    async def get_chapters(self, batch_id: str, subject_id: str) -> List[Dict]:
        """Get all chapters for a subject"""
        all_chapters = []
        page = 1
        while True:
            url = f"{self.BASE_URL}/v2/batches/{batch_id}/subject/{subject_id}/topics?page={page}"
            data = await self.fetch_data(url)
            
            if data and data.get("data"):
                all_chapters.extend(data["data"])
                page += 1
            else:
                break
        return all_chapters
    
    async def get_chapter_content(self, batch_id: str, subject_id: str, 
                                  chapter_id: str) -> Dict[str, List[str]]:
        """Get all content for a chapter"""
        content_types = ['videos', 'notes', 'DppNotes', 'DppVideos']
        content_tasks = []
        
        for content_type in content_types:
            content_tasks.append(
                self._fetch_content_by_type(batch_id, subject_id, chapter_id, content_type)
            )
        
        content_results = await asyncio.gather(*content_tasks)
        
        combined_content = {}
        for result in content_results:
            if result:
                for content_type, content_list in result.items():
                    if content_type not in combined_content:
                        combined_content[content_type] = []
                    combined_content[content_type].extend(content_list)
        
        return combined_content
    
    async def _fetch_content_by_type(self, batch_id: str, subject_id: str, 
                                     chapter_id: str, content_type: str) -> Dict[str, List[str]]:
        """Fetch content of specific type for a chapter"""
        all_schedules = []
        page = 1
        
        while True:
            params = {
                'tag': chapter_id,
                'contentType': content_type,
                'page': page
            }
            url = f"{self.BASE_URL}/v2/batches/{batch_id}/subject/{subject_id}/contents"
            data = await self.fetch_data(url, params=params)
            
            if data and data.get("success") and data.get("data"):
                for item in data["data"]:
                    item['content_type'] = content_type
                    all_schedules.append(item)
                page += 1
            else:
                break
        
        content = []
        for item in all_schedules:
            schedule_id = item["_id"]
            url = f"{self.BASE_URL}/v1/batches/{batch_id}/subject/{subject_id}/schedule/{schedule_id}/schedule-details"
            data = await self.fetch_data(url)
            
            if data and data.get("success") and data.get("data"):
                data_item = data["data"]
                
                if content_type in ("videos", "DppVideos"):
                    video_details = data_item.get('videoDetails', {})
                    if video_details:
                        name = data_item.get('topic', '')
                        video_url = video_details.get('videoUrl') or video_details.get('embedCode')
                        if video_url:
                            content.append(f"{name}:{video_url}")
                
                elif content_type in ("notes", "DppNotes"):
                    homework_ids = data_item.get('homeworkIds', [])
                    for homework in homework_ids:
                        name = homework.get('topic', '')
                        for attachment in homework.get('attachmentIds', []):
                            url_val = attachment.get('baseUrl', '') + attachment.get('key', '')
                            if url_val:
                                content.append(f"{name}:{url_val}")
        
        return {content_type: content} if content else {}
    
    async def get_todays_schedule(self, batch_id: str) -> List[str]:
        """Get today's schedule content"""
        url = f"{self.BASE_URL}/v1/batches/{batch_id}/todays-schedule"
        data = await self.fetch_data(url)
        all_content = []
        
        if data and data.get("success") and data.get("data"):
            tasks = []
            for item in data['data']:
                schedule_id = item.get('_id')
                subject_id = item.get('batchSubjectId')
                tasks.append(self._get_schedule_details(batch_id, subject_id, schedule_id))
            
            results = await asyncio.gather(*tasks)
            for result in results:
                all_content.extend(result)
        
        return all_content
    
    async def _get_schedule_details(self, batch_id: str, subject_id: str, 
                                    schedule_id: str) -> List[str]:
        """Get details for a specific schedule"""
        url = f"{self.BASE_URL}/v1/batches/{batch_id}/subject/{subject_id}/schedule/{schedule_id}/schedule-details"
        data = await self.fetch_data(url)
        content = []
        
        if data and data.get("success") and data.get("data"):
            data_item = data["data"]
            
            # Get video content
            video_details = data_item.get('videoDetails', {})
            if video_details:
                name = data_item.get('topic', '')
                video_url = video_details.get('videoUrl') or video_details.get('embedCode')
                if video_url:
                    content.append(f"{name}:{video_url}\n")
            
            # Get homework/notes content
            homework_ids = data_item.get('homeworkIds', [])
            for homework in homework_ids:
                name = homework.get('topic', '')
                for attachment in homework.get('attachmentIds', []):
                    url_val = attachment.get('baseUrl', '') + attachment.get('key', '')
                    if url_val:
                        content.append(f"{name}:{url_val}\n")
            
            # Get DPP content
            dpp = data_item.get('dpp', {})
            if dpp:
                dpp_homework_ids = dpp.get('homeworkIds', [])
                for homework in dpp_homework_ids:
                    name = homework.get('topic', '')
                    for attachment in homework.get('attachmentIds', []):
                        url_val = attachment.get('baseUrl', '') + attachment.get('key', '')
                        if url_val:
                            content.append(f"{name}:{url_val}\n")
        
        return content


@bot.on_callback_query(filters.regex("^pwwp$"))
async def pwwp_callback(bot: Client, callback_query):
    """Handle Physics Wallah callback"""
    user_id = callback_query.from_user.id
    await callback_query.answer()
    
    if not await check_user_auth(user_id, bot, callback_query.message):
        return
    
    THREADPOOL.submit(asyncio.run, process_pwwp(bot, callback_query.message, user_id))


async def process_pwwp(bot: Client, message: Message, user_id: int):
    """Process Physics Wallah download"""
    editable = await message.reply_text(
        "**Enter Working Access Token\n\nOR\n\nEnter Phone Number**"
    )
    
    try:
        # Get user input for login
        try:
            input1 = await bot.listen(
                chat_id=message.chat.id,
                filters=filters.user(user_id),
                timeout=120
            )
            raw_text1 = input1.text
            await input1.delete()
        except ListenerTimeout:
            await editable.edit("**Timeout! You took too long to respond**")
            return
        
        loop = asyncio.get_event_loop()
        connector = aiohttp.TCPConnector(limit=100, loop=loop)
        
        async with aiohttp.ClientSession(connector=connector) as session:
            downloader = PhysicsWallahDownloader(session, user_id)
            
            # Handle login
            if raw_text1.isdigit() and len(raw_text1) == 10:
                # Login with phone number
                phone = raw_text1
                await downloader.login_with_phone(phone)
                
                editable = await editable.edit("**ENTER OTP YOU RECEIVED**")
                try:
                    input2 = await bot.listen(
                        chat_id=message.chat.id,
                        filters=filters.user(user_id),
                        timeout=120
                    )
                    otp = input2.text
                    await input2.delete()
                except ListenerTimeout:
                    await editable.edit("**Timeout! You took too long to respond**")
                    return
                
                access_token = await downloader.verify_otp(phone, otp)
                await editable.edit(
                    f"<b>Physics Wallah Login Successful ✅</b>\n\n"
                    f"<pre language='Save this Login Token for future usage'>{access_token}</pre>\n\n"
                )
                editable = await message.reply_text("**Getting Batches In Your ID**")
            else:
                access_token = raw_text1
            
            downloader.HEADERS['authorization'] = f"Bearer {access_token}"
            
            # Get batches
            try:
                await downloader.get_purchased_batches()
            except Exception:
                await editable.edit(
                    "**```\nLogin Failed❗TOKEN IS EXPIRED```\n"
                    "Please Enter Working Token\n                       OR\n"
                    "Login With Phone Number**"
                )
                return
            
            # Search for batch
            await editable.edit("**Enter Your Batch Name**")
            try:
                input3 = await bot.listen(
                    chat_id=message.chat.id,
                    filters=filters.user(user_id),
                    timeout=120
                )
                batch_search = input3.text
                await input3.delete()
            except ListenerTimeout:
                await editable.edit("**Timeout! You took too long to respond**")
                return
            
            courses = await downloader.search_batches(batch_search)
            
            if not courses:
                raise Exception("No batches found for the given search name.")
            
            # Display courses and get selection
            text = ''
            for cnt, course in enumerate(courses, 1):
                text += f"{cnt}. ```\n{course['name']}```\n"
            
            await editable.edit(
                f"**Send index number of the course to download.\n\n{text}\n\n"
                f"If Your Batch Not Listed Above Enter - No**"
            )
            
            try:
                input4 = await bot.listen(
                    chat_id=message.chat.id,
                    filters=filters.user(user_id),
                    timeout=120
                )
                raw_text4 = input4.text
                await input4.delete()
            except ListenerTimeout:
                await editable.edit("**Timeout! You took too long to respond**")
                return
            
            # Handle course selection
            if input4.text.isdigit() and 1 <= int(input4.text) <= len(courses):
                selected_course = courses[int(input4.text) - 1]
            elif input4.text.lower() == "no":
                # Handle old batches
                old_batches = find_pw_old_batch(batch_search)
                if not old_batches:
                    raise Exception("No old batches found.")
                
                text = ''
                for cnt, batch in enumerate(old_batches, 1):
                    text += f"{cnt}. ```\n{batch['batch_name']}```\n"
                
                await editable.edit(f"**Send index number of the course to download.\n\n{text}**")
                
                try:
                    input5 = await bot.listen(
                        chat_id=message.chat.id,
                        filters=filters.user(user_id),
                        timeout=120
                    )
                    raw_text5 = input5.text
                    await input5.delete()
                except ListenerTimeout:
                    await editable.edit("**Timeout! You took too long to respond**")
                    return
                
                if input5.text.isdigit() and 1 <= int(input5.text) <= len(old_batches):
                    selected_course = old_batches[int(input5.text) - 1]
                else:
                    raise Exception("Invalid batch index.")
            else:
                raise Exception("Invalid batch index.")
            
            # Get download option
            await editable.edit(
                "1.```\nFull Batch```\n2.```\nToday's Class```\n3.```\nKhazana```"
            )
            
            try:
                input6 = await bot.listen(
                    chat_id=message.chat.id,
                    filters=filters.user(user_id),
                    timeout=120
                )
                raw_text6 = input6.text
                await input6.delete()
            except ListenerTimeout:
                await editable.edit("**Timeout! You took too long to respond**")
                return
            
            selected_batch_id = selected_course.get('_id') or selected_course.get('batch_id')
            selected_batch_name = selected_course.get('name') or selected_course.get('batch_name')
            clean_batch_name = clean_filename(selected_batch_name)
            clean_file_name = f"{user_id}_{clean_batch_name}"
            
            await editable.edit(f"**Extracting course : {selected_batch_name} ...**")
            start_time = time.time()
            
            if raw_text6 == '1':
                # Download full batch
                await download_full_batch(
                    bot, message, editable, downloader, session,
                    selected_batch_id, selected_batch_name, clean_file_name, user_id
                )
            elif raw_text6 == '2':
                # Download today's class
                await download_todays_class(
                    bot, message, editable, downloader,
                    selected_batch_id, selected_batch_name, clean_file_name
                )
            elif raw_text6 == '3':
                raise Exception("Working In Progress")
            else:
                raise Exception("Invalid option.")
            
            # Calculate and display time taken
            end_time = time.time()
            response_time = end_time - start_time
            formatted_time = format_time(response_time)
            
            await editable.delete()
            
            # Send files
            caption = f"**Batch Name : ```\n{selected_batch_name}``````\nTime Taken : {formatted_time}```**"
            await send_output_files(message, clean_file_name, clean_batch_name, caption)
    
    except Exception as e:
        logger.exception(f"Error in Physics Wallah download: {e}")
        try:
            await editable.edit(f"**Error : {e}**")
        except Exception:
            pass


def find_pw_old_batch(batch_search: str) -> List[Dict]:
    """Find old Physics Wallah batches"""
    try:
        response = requests.get(
            "https://abhiguru143.github.io/AS-MULTIVERSE-PW/batch/batch.json"
        )
        response.raise_for_status()
        data = response.json()
    except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
        logger.error(f"Error fetching old batches: {e}")
        return []
    
    return [
        batch for batch in data
        if batch_search.lower() in batch['batch_name'].lower()
    ]


async def download_full_batch(bot: Client, message: Message, editable: Message,
                             downloader: PhysicsWallahDownloader, session: aiohttp.ClientSession,
                             batch_id: str, batch_name: str, file_name: str, user_id: int):
    """Download full batch content"""
    batch_details = await downloader.get_batch_details(batch_id)
    
    if not batch_details or not batch_details.get("success"):
        raise Exception(f"Error fetching batch details")
    
    subjects = batch_details.get("data", {}).get("subjects", [])
    json_data = {batch_name: {}}
    all_subject_urls = {}
    
    with zipfile.ZipFile(f"{file_name}.zip", 'w') as zipf:
        for subject in subjects:
            subject_name = subject.get("subject", "Unknown Subject").replace("/", "-")
            subject_id = subject.get("_id")
            
            json_data[batch_name][subject_name] = {}
            zipf.writestr(f"{subject_name}/", "")
            
            chapters = await downloader.get_chapters(batch_id, subject_id)
            tasks = [
                downloader.get_chapter_content(batch_id, subject_id, chapter["_id"])
                for chapter in chapters
            ]
            chapter_results = await asyncio.gather(*tasks)
            
            all_urls = []
            for chapter, chapter_content in zip(chapters, chapter_results):
                chapter_name = chapter.get("name", "Unknown Chapter").replace("/", "-")
                zipf.writestr(f"{subject_name}/{chapter_name}/", "")
                json_data[batch_name][subject_name][chapter_name] = {}
                
                for content_type in ['videos', 'notes', 'DppNotes', 'DppVideos']:
                    if chapter_content.get(content_type):
                        content = chapter_content[content_type]
                        content.reverse()
                        content_string = "\n".join(content)
                        zipf.writestr(
                            f"{subject_name}/{chapter_name}/{content_type}.txt",
                            content_string.encode('utf-8')
                        )
                        json_data[batch_name][subject_name][chapter_name][content_type] = content
                        all_urls.extend(content)
            
            all_subject_urls[subject_name] = all_urls
    
    # Save JSON and text files
    with open(f"{file_name}.json", 'w') as f:
        json.dump(json_data, f, indent=4)
    
    with open(f"{file_name}.txt", 'w', encoding='utf-8') as f:
        for urls in all_subject_urls.values():
            f.write('\n'.join(urls) + '\n')


async def download_todays_class(bot: Client, message: Message, editable: Message,
                                downloader: PhysicsWallahDownloader, batch_id: str,
                                batch_name: str, file_name: str):
    """Download today's class content"""
    today_content = await downloader.get_todays_schedule(batch_id)
    
    if not today_content:
        raise Exception("No Classes Found Today")
    
    with open(f"{file_name}.txt", "w", encoding="utf-8") as f:
        f.writelines(today_content)


async def send_output_files(message: Message, file_name: str, 
                           batch_name: str, caption: str):
    """Send output files to user"""
    files = [(f"{file_name}.txt", "txt"), (f"{file_name}.zip", "zip"), 
             (f"{file_name}.json", "json")]
    
    for file_path, ext in files:
        try:
            if os.path.exists(file_path):
                with open(file_path, 'rb') as f:
                    await message.reply_document(
                        document=f,
                        caption=caption,
                        file_name=f"{batch_name}.{ext}"
                    )
        except FileNotFoundError:
            logger.error(f"File not found: {file_path}")
        except Exception as e:
            logger.exception(f"Error sending document {file_path}: {e}")
        finally:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"Removed file: {file_path}")
            except OSError as e:
                logger.error(f"Error deleting {file_path}: {e}")


# =============================================================================
# CLASSPLUS SECTION
# =============================================================================

class ClassplusDownloader:
    """Class to handle Classplus content downloading"""
    
    BASE_URL = "https://api.classplusapp.com"
    HEADERS = {
        'accept-encoding': 'gzip',
        'accept-language': 'EN',
        'api-version': '35',
        'app-version': '1.4.73.2',
        'build-number': '35',
        'connection': 'Keep-Alive',
        'content-type': 'application/json',
        'device-details': 'Xiaomi_Redmi 7_SDK-32',
        'device-id': 'c28d3cb16bbdac01',
        'host': 'api.classplusapp.com',
        'region': 'IN',
        'user-agent': 'Mobile-Android',
        'webengage-luid': '00000187-6fe4-5d41-a530-26186858be4c'
    }
    
    def __init__(self, session: aiohttp.ClientSession, user_id: int):
        self.session = session
        self.user_id = user_id
        
    async def get_hash_token(self, org_code: str) -> Optional[str]:
        """Get hash token from org code"""
        hash_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        async with self.session.get(
            f"https://{org_code}.courses.store", headers=hash_headers
        ) as response:
            html_text = await response.text()
            hash_match = re.search(r'"hash":"(.*?)"', html_text)
            return hash_match.group(1) if hash_match else None
    
    async def get_similar_courses(self, token: str, search: str = None) -> List[Dict]:
        """Get similar courses"""
        url = f"{self.BASE_URL}/v2/course/preview/similar/{token}"
        params = {'limit': 20}
        if search:
            params['search'] = search
        
        async with self.session.get(url, params=params, headers=self.HEADERS) as response:
            if response.status == 200:
                res_json = await response.json()
                return res_json.get('data', {}).get('coursesData', [])
            raise Exception(f"Failed to get courses: {response.status}")
    
    async def get_org_info(self, org_code: str, course_id: str) -> Dict:
        """Get organization info"""
        batch_headers = {
            'Accept': 'application/json, text/plain, */*',
            'region': 'IN',
            'accept-language': 'EN',
            'Api-Version': '22',
            'tutorWebsiteDomain': f'https://{org_code}.courses.store'
        }
        
        params = {'courseId': course_id}
        async with self.session.get(
            f"{self.BASE_URL}/v2/course/preview/org/info",
            params=params, headers=batch_headers
        ) as response:
            if response.status == 200:
                return await response.json()
            raise Exception(f"Failed to get org info: {response.status}")
    
    async def get_course_content(self, batch_token: str, folder_id: int = 0,
                                limit: int = 9999999999) -> Tuple[List[str], int, int, int]:
        """Get all course content recursively"""
        content_api = f'{self.BASE_URL}/v2/course/preview/content/list/{batch_token}'
        params = {'folderId': folder_id, 'limit': limit}
        
        async with self.session.get(
            content_api, params=params, headers=self.HEADERS
        ) as response:
            response.raise_for_status()
            res_json = await response.json()
            contents = res_json['data']
            
            results = []
            video_count = 0
            pdf_count = 0
            image_count = 0
            
            for content in contents:
                if content['contentType'] == 1:
                    # This is a folder
                    nested_results, nested_videos, nested_pdfs, nested_images = \
                        await self.get_course_content(batch_token, content['id'], limit)
                    results.extend(nested_results)
                    video_count += nested_videos
                    pdf_count += nested_pdfs
                    image_count += nested_images
                else:
                    # This is content
                    name = content['name']
                    url_val = content.get('url') or content.get('thumbnailUrl')
                    
                    if not url_val:
                        continue
                    
                    # Handle different URL formats
                    url_val = self._process_url_format(url_val)
                    
                    if url_val.endswith(("master.m3u8", "playlist.m3u8")):
                        signed_url = await self._get_signed_url(url_val, name)
                        if signed_url:
                            results.append(f"{name}:{url_val}\n")
                            video_count += 1
                    elif url_val:
                        results.append(f"{name}:{url_val}\n")
                        if url_val.endswith('.pdf'):
                            pdf_count += 1
                        else:
                            image_count += 1
            
            return results, video_count, pdf_count, image_count
    
    def _process_url_format(self, url: str) -> str:
        """Process different URL formats"""
        if not url:
            return None
            
        if "media-cdn.classplusapp.com/tencent/" in url:
            return url.rsplit('/', 1)[0] + "/master.m3u8"
        elif "media-cdn.classplusapp.com" in url and url.endswith('.jpg'):
            identifier = url.split('/')[-3]
            return f'https://media-cdn.classplusapp.com/alisg-cdn-a.classplusapp.com/{identifier}/master.m3u8'
        elif "cpvideocdn.testbook.com" in url and url.endswith('.png'):
            match = re.search(r'/streams/([a-f0-9]{24})/', url)
            video_id = match.group(1) if match else url.split('/')[-2]
            return f'https://cpvod.testbook.com/{video_id}/playlist.m3u8'
        elif "media-cdn.classplusapp.com/drm/" in url and url.endswith('.png'):
            video_id = url.split('/')[-3]
            return f'https://media-cdn.classplusapp.com/drm/{video_id}/playlist.m3u8'
        return url
    
    async def _get_signed_url(self, url_val: str, name: str) -> Optional[str]:
        """Get signed URL for video content"""
        max_retries = 3
        params = {"url": url_val}
        headers = {
            'x-access-token': 'eyJjb3Vyc2VJZCI6IjQ1NjY4NyIsInR1dG9ySWQiOm51bGwsIm9yZ0lkIjo0ODA2MTksImNhdGVnb3J5SWQiOm51bGx9'
        }
        
        for attempt in range(max_retries):
            try:
                async with self.session.get(
                    f"{self.BASE_URL}/cams/uploader/video/jw-signed-url",
                    params=params, headers=headers
                ) as response:
                    response.raise_for_status()
                    response_json = await response.json()
                    return response_json.get("url")
            except Exception:
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
        
        return None


@bot.on_callback_query(filters.regex("^cpwp$"))
async def cpwp_callback(bot: Client, callback_query):
    """Handle Classplus callback"""
    user_id = callback_query.from_user.id
    await callback_query.answer()
    
    if not await check_user_auth(user_id, bot, callback_query.message):
        return
    
    THREADPOOL.submit(asyncio.run, process_cpwp(bot, callback_query.message, user_id))


async def process_cpwp(bot: Client, message: Message, user_id: int):
    """Process Classplus download"""
    editable = await message.reply_text("**Enter ORG Code Of Your Classplus App**")
    
    try:
        # Get org code
        try:
            input1 = await bot.listen(
                chat_id=message.chat.id,
                filters=filters.user(user_id),
                timeout=120
            )
            org_code = input1.text.lower()
            await input1.delete()
        except ListenerTimeout:
            await editable.edit("**Timeout! You took too long to respond**")
            return
        
        loop = asyncio.get_event_loop()
        connector = aiohttp.TCPConnector(limit=100, loop=loop)
        
        async with aiohttp.ClientSession(connector=connector) as session:
            downloader = ClassplusDownloader(session, user_id)
            
            # Get hash token
            token = await downloader.get_hash_token(org_code)
            if not token:
                raise Exception('No App Found In Org Code')
            
            # Get courses
            courses = await downloader.get_similar_courses(token)
            if not courses:
                raise Exception("Didn't Find Any Course")
            
            # Display courses
            text = ''
            for cnt, course in enumerate(courses, 1):
                text += f'{cnt}. ```\n{course["name"]} 💵₹{course["finalPrice"]}```\n'
            
            await editable.edit(
                f"**Send index number of the Category Name\n\n{text}\n"
                f"If Your Batch Not Listed Then Enter Your Batch Name**"
            )
            
            # Get course selection
            try:
                input2 = await bot.listen(
                    chat_id=message.chat.id,
                    filters=filters.user(user_id),
                    timeout=120
                )
                raw_text2 = input2.text
                await input2.delete()
            except ListenerTimeout:
                await editable.edit("**Timeout! You took too long to respond**")
                return
            
            # Handle course selection
            if input2.text.isdigit() and 1 <= int(input2.text) <= len(courses):
                selected_course = courses[int(input2.text) - 1]
            else:
                # Search for specific course
                search_courses = await downloader.get_similar_courses(token, raw_text2)
                if not search_courses:
                    raise Exception("Didn't Find Any Course Matching The Search Term")
                
                text = ''
                for cnt, course in enumerate(search_courses, 1):
                    text += f'{cnt}. ```\n{course["name"]} 💵₹{course["finalPrice"]}```\n'
                
                await editable.edit(f"**Send index number of the Batch to download.\n\n{text}**")
                
                try:
                    input3 = await bot.listen(
                        chat_id=message.chat.id,
                        filters=filters.user(user_id),
                        timeout=120
                    )
                    raw_text3 = input3.text
                    await input3.delete()
                except ListenerTimeout:
                    await editable.edit("**Timeout! You took too long to respond**")
                    return
                
                if input3.text.isdigit() and 1 <= int(input3.text) <= len(search_courses):
                    selected_course = search_courses[int(input3.text) - 1]
                else:
                    raise Exception("Wrong Index Number")
            
            # Get course details
            selected_batch_id = selected_course['id']
            selected_batch_name = selected_course['name']
            clean_batch_name = clean_filename(selected_batch_name)
            clean_file_name = f"{user_id}_{clean_batch_name}"
            
            # Get batch token
            org_info = await downloader.get_org_info(org_code, selected_batch_id)
            batch_token = org_info['data']['hash']
            app_name = org_info['data']['name']
            
            await editable.edit(f"**Extracting course : {selected_batch_name} ...**")
            start_time = time.time()
            
            # Download content
            course_content, video_count, pdf_count, image_count = \
                await downloader.get_course_content(batch_token)
            
            if not course_content:
                raise Exception("Didn't Find Any Content In The Course")
            
            # Save content
            with open(f"{clean_file_name}.txt", 'w', encoding='utf-8') as f:
                f.write(''.join(course_content))
            
            # Calculate time
            end_time = time.time()
            formatted_time = format_time(end_time - start_time)
            
            await editable.delete()
            
            # Send file
            caption = (
                f"**App Name : ```\n{app_name}({org_code})```\n"
                f"Batch Name : ```\n{selected_batch_name}```"
                f"```\n🎬 : {video_count} | 📁 : {pdf_count} | 🖼 : {image_count}```"
                f"```\nTime Taken : {formatted_time}```**"
            )
            
            with open(f"{clean_file_name}.txt", 'rb') as f:
                await message.reply_document(
                    document=f,
                    caption=caption,
                    file_name=f"{clean_batch_name}.txt"
                )
            
            os.remove(f"{clean_file_name}.txt")
    
    except Exception as e:
        logger.exception(f"Error in Classplus download: {e}")
        try:
            await editable.edit(f"**Error : {e}**")
        except Exception:
            pass


# =============================================================================
# APPX SECTION
# =============================================================================

class AppxDownloader:
    """Class to handle Appx content downloading"""
    
    def __init__(self, session: aiohttp.ClientSession, user_id: int):
        self.session = session
        self.user_id = user_id
        self.token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpZCI6IjEwMTU1NTYyIiwiZW1haWwiOiJhbm9ueW1vdXNAZ21haWwuY29tIiwidGltZXN0YW1wIjoxNzQ1MDc5MzgyLCJ0ZW5hbnRUeXBlIjoidXNlciIsInRlbmFudE5hbWUiOiIiLCJ0ZW5hbnRJZCI6IiIsImRpc3Bvc2FibGUiOmZhbHNlfQ.EfwLhNtbzUVs1qRkMqc3P6ObkKSO0VYWKdAe6GmhdAg"
        self.userid = "10155562"
        
    @staticmethod
    def decrypt_url(encrypted: str) -> str:
        """Decrypt Appx encrypted URL"""
        try:
            enc = b64decode(encrypted.split(':')[0])
            key = '638udh3829162018'.encode('utf-8')
            iv = 'fedcba9876543210'.encode('utf-8')
            
            if len(enc) == 0:
                return ""
            
            cipher = AES.new(key, AES.MODE_CBC, iv)
            plaintext = unpad(cipher.decrypt(enc), AES.block_size)
            return plaintext.decode('utf-8')
        except Exception:
            return ""
    
    async def fetch_data(self, url: str, headers: Dict = None, 
                        data: Dict = None) -> Optional[Dict]:
        """Fetch data from API with JSON parsing"""
        try:
            if data:
                async with self.session.post(url, headers=headers, data=data) as response:
                    text = await response.text()
            else:
                async with self.session.get(url, headers=headers) as response:
                    text = await response.text()
            
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                # Try to extract JSON from response
                match = re.search(r'\{"status":', text, re.DOTALL)
                if match:
                    json_str = text[match.start():]
                    # Find matching closing brace
                    open_braces = 0
                    json_end = -1
                    for i, char in enumerate(json_str):
                        if char == '{':
                            open_braces += 1
                        elif char == '}':
                            open_braces -= 1
                        if open_braces == 0:
                            json_end = i + 1
                            break
                    
                    if json_end != -1:
                        return json.loads(json_str[:json_end])
                
                return None
        except Exception as e:
            logger.error(f"Error fetching data: {e}")
            return None
    
    async def get_courses(self, api: str) -> List[Dict]:
        """Get all courses from API"""
        headers = self._get_headers()
        
        res1 = await self.fetch_data(f"{api}/get/courselist", headers)
        res2 = await self.fetch_data(f"{api}/get/courselistnewv2", headers)
        
        courses = []
        
        if res1 and res1.get('status') == 200:
            courses.extend(res1.get("data", []))
        
        if res2 and res2.get('status') == 200:
            courses.extend(res2.get("data", []))
        
        return courses
    
    def _get_headers(self) -> Dict:
        """Get headers for API requests"""
        return {
            'User-Agent': "okhttp/4.9.1",
            'Accept-Encoding': "gzip",
            'client-service': "Appx",
            'auth-key': "appxapi",
            'user-id': self.userid,
            'authorization': self.token,
            'user_app_category': "",
            'language': "en",
            'device_type': "ANDROID"
        }
    
    async def process_folder_wise_course(self, api: str, course_id: str, 
                                        folder_wise: int) -> List[str]:
        """Process course based on folder_wise_course flag"""
        headers = self._get_headers()
        
        if folder_wise == 0:
            return await self._process_non_folder(api, course_id, headers)
        elif folder_wise == 1:
            return await self._process_folder(api, course_id, headers)
        else:
            # Try both methods
            results = []
            results.extend(await self._process_non_folder(api, course_id, headers))
            results.extend(await self._process_folder(api, course_id, headers))
            return results
    
    async def _process_non_folder(self, api: str, course_id: str, 
                                  headers: Dict) -> List[str]:
        """Process non-folder-wise course"""
        results = []
        
        # Get subjects
        res = await self.fetch_data(
            f"{api}/get/allsubjectfrmlivecourseclass?courseid={course_id}&start=-1",
            headers
        )
        
        if not res or "data" not in res:
            return results
        
        for subject in res["data"]:
            subject_id = subject.get("subjectid")
            
            # Get topics
            res2 = await self.fetch_data(
                f"{api}/get/alltopicfrmlivecourseclass?courseid={course_id}&subjectid={subject_id}&start=-1",
                headers
            )
            
            if not res2 or "data" not in res2:
                continue
            
            for topic in res2["data"]:
                topic_id = topic.get("topicid")
                
                # Get content
                res3 = await self.fetch_data(
                    f"{api}/get/livecourseclassbycoursesubtopconceptapiv3?"
                    f"topicid={topic_id}&start=-1&courseid={course_id}&subjectid={subject_id}",
                    headers
                )
                
                if not res3 or "data" not in res3:
                    continue
                
                for item in res3["data"]:
                    content = self._extract_content(item, api, course_id, headers)
                    if content:
                        results.extend(content)
        
        return results
    
    async def _process_folder(self, api: str, course_id: str, 
                              headers: Dict, parent_id: int = -1) -> List[str]:
        """Process folder-wise course"""
        results = []
        
        res = await self.fetch_data(
            f"{api}/get/folder_contentsv2?course_id={course_id}&parent_id={parent_id}",
            headers
        )
        
        if not res or "data" not in res:
            return results
        
        for item in res["data"]:
            if item.get("material_type") == "FOLDER":
                nested_results = await self._process_folder(
                    api, course_id, headers, item.get("id")
                )
                results.extend(nested_results)
            else:
                content = self._extract_content(item, api, course_id, headers)
                if content:
                    results.extend(content)
        
        return results
    
    def _extract_content(self, item: Dict, api: str, course_id: str, 
                        headers: Dict) -> List[str]:
        """Extract content from item"""
        results = []
        title = item.get("Title", "")
        material_type = item.get("material_type", "")
        
        if material_type == "PDF" or material_type == "TEST":
            # Extract PDF links
            pdf_link = self.decrypt_url(item.get("pdf_link", ""))
            if pdf_link and pdf_link.endswith(".pdf"):
                if item.get("is_pdf_encrypted"):
                    key = self.decrypt_url(item.get("pdf_encryption_key", ""))
                    results.append(f"{title}:{pdf_link}*{key}\n" if key else f"{title}:{pdf_link}\n")
                else:
                    results.append(f"{title}:{pdf_link}\n")
            
            pdf_link2 = self.decrypt_url(item.get("pdf_link2", ""))
            if pdf_link2 and pdf_link2.endswith(".pdf"):
                if item.get("is_pdf2_encrypted"):
                    key = self.decrypt_url(item.get("pdf2_encryption_key", ""))
                    results.append(f"{title}:{pdf_link2}*{key}\n" if key else f"{title}:{pdf_link2}\n")
                else:
                    results.append(f"{title}:{pdf_link2}\n")
        
        elif material_type == "IMAGE":
            thumbnail = item.get("thumbnail")
            if thumbnail:
                results.append(f"{title}:{thumbnail}\n")
        
        elif material_type == "VIDEO":
            # This would need async handling, simplified here
            pass
        
        return results


def find_appx_matching_apis(search_terms: List[str], file_path: str = "appxapis.json") -> List[Dict]:
    """Find matching Appx APIs from JSON file"""
    matched_apis = []
    
    try:
        with open(file_path, 'r') as f:
            api_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"Error reading API file: {e}")
        return matched_apis
    
    for item in api_data:
        for term in search_terms:
            term = term.strip().lower()
            if term in item["name"].lower() or term in item["api"].lower():
                matched_apis.append(item)
                break
    
    # Remove duplicates
    unique_apis = []
    seen = set()
    for item in matched_apis:
        if item["api"] not in seen:
            unique_apis.append(item)
            seen.add(item["api"])
    
    return unique_apis


@bot.on_callback_query(filters.regex("^appxwp$"))
async def appxwp_callback(bot: Client, callback_query):
    """Handle Appx callback"""
    user_id = callback_query.from_user.id
    await callback_query.answer()
    
    if not await check_user_auth(user_id, bot, callback_query.message):
        return
    
    THREADPOOL.submit(asyncio.run, process_appxwp(bot, callback_query.message, user_id))


async def process_appxwp(bot: Client, message: Message, user_id: int):
    """Process Appx download"""
    editable = await message.reply_text("**Enter App Name Or Api**")
    
    try:
        # Get API/App name
        try:
            input1 = await bot.listen(
                chat_id=message.chat.id,
                filters=filters.user(user_id),
                timeout=120
            )
            raw_text1 = input1.text
            await input1.delete()
        except ListenerTimeout:
            await editable.edit("**Timeout! You took too long to respond**")
            return
        
        loop = asyncio.get_event_loop()
        connector = aiohttp.TCPConnector(limit=100, loop=loop)
        
        async with aiohttp.ClientSession(connector=connector) as session:
            downloader = AppxDownloader(session, user_id)
            
            # Determine API URL
            if raw_text1.startswith(("http://", "https://")):
                api = raw_text1.rstrip("/")
                selected_app_name = api
            else:
                # Search for matching APIs
                search_terms = [term.strip() for term in raw_text1.split()]
                matches = find_appx_matching_apis(search_terms)
                
                if not matches:
                    raise Exception("No matches found. Enter Correct App Starting Word")
                
                text = ''
                for cnt, item in enumerate(matches, 1):
                    text += f'{cnt}. ```\n{item["name"]}:{item["api"]}```\n'
                
                await editable.edit(
                    f"**Send index number of the Batch to download.\n\n{text}**"
                )
                
                try:
                    input2 = await bot.listen(
                        chat_id=message.chat.id,
                        filters=filters.user(user_id),
                        timeout=120
                    )
                    raw_text2 = input2.text
                    await input2.delete()
                except ListenerTimeout:
                    await editable.edit("**Timeout! You took too long to respond**")
                    return
                
                if input2.text.isdigit() and 1 <= int(input2.text) <= len(matches):
                    selected = matches[int(input2.text) - 1]
                    api = selected['api']
                    selected_app_name = selected['name']
                else:
                    raise Exception("Wrong Index Number")
            
            # Get courses
            courses = await downloader.get_courses(api)
            
            if not courses:
                raise Exception("Did not found any course")
            
            # Display courses
            if len(courses) > 50:
                # Save to file
                text = ''
                for cnt, course in enumerate(courses, 1):
                    text += f'{cnt}. {course["course_name"]} 💵₹{course.get("price", "N/A")}\n'
                
                file_name = f"{user_id}_paid_course_details"
                with open(f"{file_name}.txt", 'w') as f:
                    f.write(text)
                
                caption = f"**App Name : ```\n{selected_app_name}```\nBatch Name : ```\nPaid Course Details```**"
                
                await editable.delete()
                with open(f"{file_name}.txt", 'rb') as f:
                    await message.reply_document(
                        document=f,
                        caption=caption,
                        file_name="paid course details.txt"
                    )
                os.remove(f"{file_name}.txt")
                
                editable = await message.reply_text(
                    "**Send index number From the course details txt File to download.**"
                )
            else:
                text = ''
                for cnt, course in enumerate(courses, 1):
                    text += f'{cnt}. ```\n{course["course_name"]} 💵₹{course.get("price", "N/A")}```\n'
                await editable.edit(
                    f"**Send index number of the course to download.\n\n{text}**"
                )
            
            # Get course selection
            try:
                input5 = await bot.listen(
                    chat_id=message.chat.id,
                    filters=filters.user(user_id),
                    timeout=120
                )
                raw_text5 = input5.text
                await input5.delete()
            except ListenerTimeout:
                await editable.edit("**Timeout! You took too long to respond**")
                return
            
            if not input5.text.isdigit() or not (1 <= int(input5.text) <= len(courses)):
                raise Exception("Wrong Index Number")
            
            selected_course = courses[int(input5.text) - 1]
            selected_batch_id = selected_course['id']
            selected_batch_name = selected_course['course_name']
            folder_wise = selected_course.get("folder_wise_course", 0)
            
            clean_batch_name = clean_filename(selected_batch_name, 244)
            clean_file_name = f"{user_id}_{clean_batch_name}"
            
            await editable.edit(f"**Extracting course : {selected_batch_name} ...**")
            start_time = time.time()
            
            # Process course
            all_outputs = await downloader.process_folder_wise_course(
                api, selected_batch_id, folder_wise
            )
            
            if not all_outputs:
                raise Exception("Didn't Found Any Content In The Course")
            
            # Save content
            with open(f"{clean_file_name}.txt", 'w') as f:
                for output_line in all_outputs:
                    f.write(output_line)
            
            # Calculate time
            end_time = time.time()
            formatted_time = format_time(end_time - start_time)
            
            caption = (
                f"**App Name : ```\n{selected_app_name}```\n"
                f"Batch Name : ```\n{selected_batch_name}```"
                f"```\nTime Taken : {formatted_time}```**"
            )
            
            await editable.delete()
            
            with open(f"{clean_file_name}.txt", 'rb') as f:
                await message.reply_document(
                    document=f,
                    caption=caption,
                    file_name=f"{clean_batch_name}.txt"
                )
            
            os.remove(f"{clean_file_name}.txt")
    
    except Exception as e:
        logger.exception(f"Error in Appx download: {e}")
        try:
            await editable.edit(f"**Error : {e}**")
        except Exception:
            pass


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    print("Bot starting...")
    bot.run()
