import socket
import threading
import queue
import time
import re
import requests

# ========================
# 配置参数
# ========================
TEST_TIMEOUT = 3
TEST_PORT = 443
MAX_THREADS = 10
TOP_NODES = 80
TXT_OUTPUT_FILE = "HK.txt"

# 每个网段采样范围
SAMPLE_THIRD_RANGE = range(0, 8)   # 第三段
SAMPLE_FOURTH_RANGE = range(1, 51) # 第四段（越多越精确）

# ========================
# 国家代码映射
# ========================
COUNTRY_CODES = {
    "HK": "中国香港",
    "JP": "日本",
    "US": "美国",
    "SG": "新加坡",
    "TW": "中国台湾",
    "DE": "德国",
    "GB": "英国",
    "KR": "韩国",
    "FR": "法国",
    "IN": "印度",
    "CN": "中国",
}

# ========================
# 获取IP国家
# ========================
def get_ip_country(ip):
    if not ip or not re.match(r"^\d{1,3}(\.\d{1,3}){3}$", ip):
        return "未知"
    try:
        resp = requests.get(f"https://ipwhois.app/json/{ip}", timeout=5)
        data = resp.json()
        country = data.get("country", "")
        code = data.get("country_code") or data.get("countryCode")
        if country.lower() == "hong kong":
            return "中国香港"
        if code:
            return COUNTRY_CODES.get(code.upper(), country)
        return country or "未知"
    except Exception:
        pass

    try:
        resp = requests.get(f"http://ip-api.com/json/{ip}?fields=status,country,countryCode", timeout=5)
        data = resp.json()
        if data.get("status") == "success":
            country = data.get("country", "")
            code = data.get("countryCode")
            if country.lower() == "hong kong":
                return "中国香港"
            if code:
                return COUNTRY_CODES.get(code.upper(), country)
            return country or "未知"
    except Exception:
        pass
    return "未知"

# ========================
# IP清洗
# ========================
def clean_ip(ip):
    ip = ip.strip()
    if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", ip):
        parts = ip.split(".")
        if all(0 <= int(p) <= 255 for p in parts):
            return ip
    return None

# ========================
# Cloudflare节点测试类
# ========================
class CloudflareNodeTester:
    def __init__(self):
        self.nodes = []
        self.results = []
        self.lock = threading.Lock()

    def fetch_known_nodes(self):
        """
        常见 Cloudflare 网段采样生成 IPv4
        """
        base_ranges = [
            "104.16", "104.17", "104.18", "104.19", "104.20",
            "141.101", "162.158", "162.159", "172.64", "172.65", "172.66",
            "188.114",
        ]

        nodes = []
        for base in base_ranges:
            parts = base.rstrip(".").split(".")
            if len(parts) == 2:
                a, b = parts
                for third in SAMPLE_THIRD_RANGE:
                    for fourth in SAMPLE_FOURTH_RANGE:
                        ip = f"{a}.{b}.{third}.{fourth}"
                        nodes.append(ip)
            elif len(parts) == 3:
                a, b, c = parts
                for fourth in SAMPLE_FOURTH_RANGE:
                    ip = f"{a}.{b}.{c}.{fourth}"
                    nodes.append(ip)
        return list(dict.fromkeys(nodes))

    def test_node_speed_once(self, ip):
        try:
            start = time.time()
            sock = socket.create_connection((ip, TEST_PORT), timeout=TEST_TIMEOUT)
            sock.close()
            latency = (time.time() - start) * 1000.0
            return latency
        except Exception:
            return None

    def worker(self, q):
        while True:
            ip = q.get()
            if ip is None:
                q.task_done()
                break
            latency = self.test_node_speed_once(ip)
            if latency is not None:
                with self.lock:
                    self.results.append((ip, latency))
            q.task_done()

    def test_all_nodes(self):
        q = queue.Queue()
        for ip in self.nodes:
            q.put(ip)
        threads = []
        for _ in range(min(MAX_THREADS, len(self.nodes))):
            t = threading.Thread(target=self.worker, args=(q,))
            t.daemon = True
            t.start()
            threads.append(t)
        q.join()
        for _ in threads:
            q.put(None)
        for t in threads:
            t.join()

    def sort_and_display_results(self):
        sorted_results = sorted(self.results, key=lambda x: x[1])[:TOP_NODES]
        print("\n📡 正在查询最快节点的国家信息...\n")
        display_list = []
        for ip, latency in sorted_results:
            country = get_ip_country(ip)
            display_list.append((ip, latency, country))

        hk_list = [r for r in display_list if "香港" in r[2] or "Hong Kong" in r[2]]
        if not hk_list:
            print("⚠️ 未检测到香港节点（API定位可能受限），将保存全部节点。")
            hk_list = display_list

        print("\n🏁 最快节点:")
        for ip, lat, country in hk_list:
            print(f"{ip:<16} {lat:7.2f} ms   {country}")

        self.save_results(hk_list)

    def save_results(self, results):
        try:
            with open(TXT_OUTPUT_FILE, "w", encoding="utf-8") as f:
                for ip, latency, country in results:
                    f.write(f"{ip}:{TEST_PORT} #{country} {int(latency)}ms\n")
            print(f"\n✅ 已保存 {len(results)} 条结果到 {TXT_OUTPUT_FILE}")
        except Exception as e:
            print(f"保存失败: {e}")

    def run(self):
        print("🚀 正在生成 Cloudflare 节点采样...")
        self.nodes = self.fetch_known_nodes()
        print(f"生成 {len(self.nodes)} 个节点，开始测速（{MAX_THREADS} 并发）...\n")
        self.test_all_nodes()
        if not self.results:
            print("❌ 无可连通节点。")
            return
        self.sort_and_display_results()

# ========================
# 主执行
# ========================
if __name__ == "__main__":
    tester = CloudflareNodeTester()
    tester.run()
