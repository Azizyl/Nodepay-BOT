from aiohttp import ClientResponseError, ClientSession, ClientTimeout
from aiohttp_socks import ProxyConnector
from fake_useragent import FakeUserAgent
from curl_cffi import requests
from datetime import datetime
import asyncio, time, base64, json, os, uuid, pytz

from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text
from rich.console import Console

# Set zona waktu
wib = pytz.timezone('Asia/Jakarta')
console = Console()

class Nodepay:
    def __init__(self) -> None:
        self.headers = {
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://app.nodepay.ai",
            "Referer": "https://app.nodepay.ai/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "cross-site",
            "User-Agent": FakeUserAgent().random
        }
        self.proxies = []
        self.proxy_index = 0
        self.account_proxies = {}

        # Counter UI
        self.total_accounts = 0
        self.success_count = 0
        self.processing_count = 0
        self.fail_count = 0

        # Daftar untuk menyimpan log (akan ditampilkan di panel bawah)
        self.log_lines = []

    def log(self, message):
        """Tambahkan pesan log dengan timestamp ke daftar log."""
        timestamp = datetime.now().astimezone(wib).strftime('%x %X %Z')
        self.log_lines.append(f"[{timestamp}] {message}")

    def welcome(self):
        welcome_text = "Auto Ping Nodepay - BOT\nRey? <INI WATERMARK>"
        self.log(welcome_text)

    def make_layout(self):
        """Membuat layout dengan header status di atas dan panel log di bawah."""
        header_text = (
            "═══════════════════════\n"
            f"✅ Akun Berhasil : {self.success_count}\n"
            f"⏳ Akun Diproses : {self.processing_count}\n"
            f"❌ Akun Gagal : {self.fail_count}\n"
            "═══════════════════════"
        )
        header_panel = Panel(Text(header_text, justify="center"), title="Status")
        # Tampilkan 20 log terakhir
        log_text = "\n".join(self.log_lines[-20:])
        log_panel = Panel(Text(log_text), title="Log yang berjalan", height=20)
        layout = Layout()
        layout.split_column(
            Layout(header_panel, size=7),
            Layout(log_panel)
        )
        return layout

    async def ui_updater(self, live):
        """Task yang secara berkala memperbarui tampilan UI."""
        while True:
            live.update(self.make_layout())
            await asyncio.sleep(1)

    async def load_proxies(self, use_proxy_choice: int):
        filename = "proxy.txt"
        try:
            if use_proxy_choice == 1:
                async with ClientSession(timeout=ClientTimeout(total=30)) as session:
                    async with session.get("https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/all.txt") as response:
                        response.raise_for_status()
                        content = await response.text()
                        with open(filename, 'w') as f:
                            f.write(content)
                        self.proxies = content.splitlines()
            else:
                if not os.path.exists(filename):
                    self.log(f"File {filename} Not Found.")
                    return
                with open(filename, 'r') as f:
                    self.proxies = f.read().splitlines()

            if not self.proxies:
                self.log("No Proxies Found.")
                return

            self.log(f"Proxies Total: {len(self.proxies)}")

        except Exception as e:
            self.log(f"Failed To Load Proxies: {e}")
            self.proxies = []

    def check_proxy_schemes(self, proxies):
        schemes = ["http://", "https://", "socks4://", "socks5://"]
        if any(proxies.startswith(scheme) for scheme in schemes):
            return proxies
        return f"http://{proxies}"

    def get_next_proxy_for_account(self, account):
        if account not in self.account_proxies:
            if not self.proxies:
                return None
            proxy = self.check_proxy_schemes(self.proxies[self.proxy_index])
            self.account_proxies[account] = proxy
            self.proxy_index = (self.proxy_index + 1) % len(self.proxies)
        return self.account_proxies[account]

    def rotate_proxy_for_account(self, account):
        if not self.proxies:
            return None
        proxy = self.check_proxy_schemes(self.proxies[self.proxy_index])
        self.account_proxies[account] = proxy
        self.proxy_index = (self.proxy_index + 1) % len(self.proxies)
        return proxy

    def decode_token(self, token: str):
        try:
            header, payload, signature = token.split(".")
            decoded_payload = base64.urlsafe_b64decode(payload + "==").decode("utf-8")
            parsed_payload = json.loads(decoded_payload)
            user_id = parsed_payload["sub"]
            return user_id
        except Exception:
            return None

    def generate_browser_id(self):
        return str(uuid.uuid4())

    def mask_account(self, account):
        return account[:3] + '*' * 3 + account[-3:]

    def print_message(self, account, proxy, message):
        self.log(f"[Account: {account}] [Proxy: {proxy}] {message}")

    async def print_question(self):
        while True:
            try:
                self.log("1. Run With Monosans Proxy")
                self.log("2. Run With Private Proxy")
                self.log("3. Run Without Proxy")
                choice = int(console.input("Choose [1/2/3] -> ").strip())
                if choice in [1, 2, 3]:
                    proxy_type = (
                        "Run With Monosans Proxy" if choice == 1 else
                        "Run With Private Proxy" if choice == 2 else
                        "Run Without Proxy"
                    )
                    self.log(f"{proxy_type} Selected.")
                    return choice
                else:
                    self.log("Please enter either 1, 2 or 3.")
            except ValueError:
                self.log("Invalid input. Enter a number (1, 2 or 3).")

    async def user_session(self, token: str, proxy=None, retries=5):
        url = "http://api.nodepay.ai/api/auth/session"
        headers = {
            **self.headers,
            "Authorization": f"Bearer {token}",
            "Content-Length": "2",
            "Content-Type": "application/json",
        }
        for attempt in range(retries):
            connector = ProxyConnector.from_url(proxy) if proxy else None
            try:
                async with ClientSession(connector=connector, timeout=ClientTimeout(total=60)) as session:
                    async with session.post(url=url, headers=headers, json={}) as response:
                        if response.status == 401:
                            self.print_message(self.mask_account(token), proxy, "GET User Session Failed: Np Token Expired")
                            return None
                        response.raise_for_status()
                        result = await response.json()
                        return result['data']
            except (Exception, ClientResponseError) as e:
                if attempt < retries - 1:
                    await asyncio.sleep(5)
                    continue
                self.print_message(self.mask_account(token), proxy, f"GET User Session Failed: {str(e)}")
                return None

    async def user_earning(self, token: str, username: str, proxy=None, retries=5):
        url = "http://api.nodepay.ai/api/earn/info"
        headers = {
            **self.headers,
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        for attempt in range(retries):
            connector = ProxyConnector.from_url(proxy) if proxy else None
            try:
                async with ClientSession(connector=connector, timeout=ClientTimeout(total=60)) as session:
                    async with session.get(url=url, headers=headers) as response:
                        if response.status == 401:
                            self.print_message(username, proxy, "GET Earning Data Failed: Np Token Expired")
                            return None
                        response.raise_for_status()
                        result = await response.json()
                        return result['data']
            except (Exception, ClientResponseError) as e:
                if attempt < retries - 1:
                    await asyncio.sleep(5)
                    continue
                self.print_message(username, proxy, f"GET Earning Data Failed: {str(e)}")
                return None

    async def mission_lists(self, token: str, username: str, proxy=None, retries=5):
        url = "http://api.nodepay.ai/api/mission"
        headers = {
            **self.headers,
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        for attempt in range(retries):
            connector = ProxyConnector.from_url(proxy) if proxy else None
            try:
                async with ClientSession(connector=connector, timeout=ClientTimeout(total=60)) as session:
                    async with session.get(url=url, headers=headers) as response:
                        if response.status == 401:
                            self.print_message(username, proxy, "GET Available Mission Failed: Np Token Expired")
                            return None
                        response.raise_for_status()
                        result = await response.json()
                        return result['data']
            except (Exception, ClientResponseError) as e:
                if attempt < retries - 1:
                    await asyncio.sleep(5)
                    continue
                self.print_message(username, proxy, f"GET Available Mission Failed: {str(e)}")
                return None

    async def complete_missions(self, token: str, username: str, mission_id: str, proxy=None, retries=5):
        url = "http://api.nodepay.ai/api/mission/complete-mission"
        data = json.dumps({'mission_id': mission_id})
        headers = {
            **self.headers,
            "Authorization": f"Bearer {token}",
            "Content-Length": str(len(data)),
            "Content-Type": "application/json",
        }
        for attempt in range(retries):
            connector = ProxyConnector.from_url(proxy) if proxy else None
            try:
                async with ClientSession(connector=connector, timeout=ClientTimeout(total=60)) as session:
                    async with session.post(url=url, headers=headers, data=data) as response:
                        if response.status == 401:
                            self.print_message(username, proxy, "Complete Available Mission Failed: Np Token Expired")
                            return None
                        response.raise_for_status()
                        result = await response.json()
                        return result['data']
            except (Exception, ClientResponseError) as e:
                if attempt < retries - 1:
                    await asyncio.sleep(5)
                    continue
                self.print_message(username, proxy, f"Complete Available Mission Failed: {str(e)}")
                return None

    async def send_ping(self, token: str, user_id: str, username: str, browser_id: str, num_id: int, use_proxy: bool, proxy=None, retries=5):
        url = "https://nw.nodepay.org/api/network/ping"
        data = json.dumps({
            "id": user_id,
            "browser_id": browser_id,
            "timestamp": int(time.time()),
            "version": "2.2.7"
        })
        headers = {
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Authorization": f"Bearer {token}",
            "Content-Length": str(len(data)),
            "Content-Type": "application/json",
            "Origin": "chrome-extension://lgmpfmgeabnnlemejacfljbmonaomfmm",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "cross-site",
            "User-Agent": FakeUserAgent().random
        }
        for attempt in range(retries):
            try:
                response = await asyncio.to_thread(
                    requests.post, url=url, headers=headers, data=data,
                    proxy=proxy, timeout=60, impersonate="safari15_5"
                )
                if response.status_code == 401:
                    self.print_message(username, proxy, f"PING Failed - Browser ID {num_id}: {browser_id} - Reason: Np Token Expired")
                    return None
                response.raise_for_status()
                result = response.json()
                return result['data']['ip_score']
            except Exception as e:
                if attempt < retries - 1:
                    await asyncio.sleep(5)
                    continue
                self.print_message(username, proxy, f"PING Failed - Browser ID {num_id}: {browser_id} - Reason: {str(e)}")
                if use_proxy:
                    proxy = self.rotate_proxy_for_account(browser_id)
                return None

    async def process_user_earning(self, token: str, user_id: str, username: str, use_proxy: bool):
        while True:
            proxy = self.get_next_proxy_for_account(user_id) if use_proxy else None
            earning = await self.user_earning(token, username, proxy)
            if earning:
                season_name = earning.get('season_name', 'Season #N/A')
                today_point = earning.get('today_earning', 'N/A')
                total_point = earning.get('total_earning', 'N/A')
                current_point = earning.get('current_point', 'N/A')
                pending_point = earning.get('pending_point', 'N/A')
                self.print_message(username, proxy,
                    f"Earning {season_name} - Today {today_point} PTS - Total {total_point} PTS - Current {current_point} PTS - Pending {pending_point} PTS")
            await asyncio.sleep(30 * 60)

    async def process_user_missions(self, token: str, user_id: str, username: str, use_proxy: bool):
        while True:
            proxy = self.get_next_proxy_for_account(user_id) if use_proxy else None
            missions = await self.mission_lists(token, username, proxy)
            if missions:
                completed = False
                for mission in missions:
                    mission_id = mission['id']
                    title = mission['title']
                    reward = mission['point']
                    status = mission['status']
                    if mission and status == "AVAILABLE":
                        complete = await self.complete_missions(token, username, mission_id, proxy)
                        if complete:
                            self.print_message(username, proxy, f"Mission {title} Is Completed - Reward: {reward} PTS")
                        else:
                            self.print_message(username, proxy, f"Mission {title} Isn't Completed")
                    else:
                        completed = True
                if completed:
                    self.print_message(username, proxy, "All Available Mission Is Completed")
            await asyncio.sleep(12 * 60 * 60)

    async def connection_state(self, token: str, user_id, username: str, browser_id: str, num_id: int, use_proxy: bool):
        while True:
            proxy = self.get_next_proxy_for_account(browser_id) if use_proxy else None
            self.log(f"Trying to send Ping for Browser ID {num_id}: {browser_id}...")
            result = await self.send_ping(token, user_id, username, browser_id, num_id, use_proxy, proxy)
            if result is not None:
                self.print_message(username, proxy, f"PING Success - Browser ID {num_id}: {browser_id} - IP Score: {result}")
            self.log("Waiting for 55 Minutes for next Ping...")
            await asyncio.sleep(55 * 60)

    async def process_get_user_session(self, token: str, user_id: str, use_proxy: bool):
        proxy = self.get_next_proxy_for_account(user_id) if use_proxy else None
        user = None
        while user is None:
            user = await self.user_session(token, proxy)
            if not user:
                self.fail_count += 1
                self.processing_count -= 1
                proxy = self.rotate_proxy_for_account(user_id) if use_proxy else None
                await asyncio.sleep(5)
                continue
            self.print_message(self.mask_account(token), proxy, "GET User Session Success")
            self.success_count += 1
            self.processing_count -= 1
            return user

    async def process_accounts(self, token: str, user_id: str, use_proxy: bool):
        user = await self.process_get_user_session(token, user_id, use_proxy)
        if user:
            username = user.get("name")
            tasks = []
            tasks.append(asyncio.create_task(self.process_user_earning(token, user_id, username, use_proxy)))
            tasks.append(asyncio.create_task(self.process_user_missions(token, user_id, username, use_proxy)))
            if use_proxy:
                for i in range(3):
                    num_id = i + 1
                    browser_id = self.generate_browser_id()
                    tasks.append(asyncio.create_task(self.connection_state(token, user_id, username, browser_id, num_id, use_proxy)))
            else:
                num_id = 1
                browser_id = self.generate_browser_id()
                tasks.append(asyncio.create_task(self.connection_state(token, user_id, username, browser_id, num_id, use_proxy)))
            await asyncio.gather(*tasks)

    async def main(self):
        try:
            with open('tokens.txt', 'r') as file:
                tokens = [line.strip() for line in file if line.strip()]
            use_proxy_choice = await self.print_question()
            use_proxy = False
            if use_proxy_choice in [1, 2]:
                use_proxy = True
            self.total_accounts = len(tokens)
            self.processing_count = self.total_accounts
            if use_proxy:
                await self.load_proxies(use_proxy_choice)
            # Mulai UI Live sehingga header selalu terlihat di atas dan log di bawah
            with Live(self.make_layout(), refresh_per_second=1, screen=True) as live:
                ui_task = asyncio.create_task(self.ui_updater(live))
                while True:
                    tasks = []
                    for token in tokens:
                        if token:
                            user_id = self.decode_token(token)
                            if user_id:
                                tasks.append(self.process_accounts(token, user_id, use_proxy))
                    await asyncio.gather(*tasks)
                    await asyncio.sleep(10)
        except FileNotFoundError:
            self.log("File 'tokens.txt' Not Found.")
        except Exception as e:
            self.log(f"Error: {e}")

if __name__ == "__main__":
    try:
        bot = Nodepay()
        asyncio.run(bot.main())
    except KeyboardInterrupt:
        print("Exiting Nodepay BOT")