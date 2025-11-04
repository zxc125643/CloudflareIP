import socket
import threading
import queue
import time
import json
import re
import requests

# ========================
# 参数配置
# ========================
TEST_TIMEOUT = 3          # 单个节点超时时间（秒）
TEST_PORT = 443           # 测试端口
MAX_THREADS = 3           # 并发线程数
TOP_NODES = 20            # 取前 20 个节点
TXT_OUTPUT_FILE = "HK.txt"  # 输出文件名

# ========================
# 国家代码映射
# ========================
COUNTRY_CODES = {
    "HK": "香港",
    "JP": "日本",
    "US": "美国",
    "SG": "新加坡",
    "TW": "台湾",
    "DE": "德国",
    "GB": "英国",
    "KR": "韩国",
    "FR": "法国",
    "IN": "印度",
    "CN": "中国",
}

# ========================
# IP 国家查询函数
# ========================
def get_ip_country(ip):
    if not ip or not re.match(r"^\d{1,3}(\.\d{1,3}){3}$", ip):
        return "未知"

    try:
        response = requests.get(f"https://ipwhois.app/json/{ip}", timeout=3)
        data = response.json()
        country_code = data.get("country_code", "")
        country_name = COUNTRY_CODES.get(country_code, data.get("country", "未知"))
        return country_name
    except Exception:
        try:
            response = requests.get(f"http://ip-api.com/json/{ip}", timeout=3)
            data = response.json()
            country_code = data.get("countryCode", "")
            country_name = COUNTRY_CODES.get(country_code, data.get("country", "未知"))
            return country_name
        except Exception:
            return "未知"

# ========================
# IP 清理函数
# ========================
def clean_ip(ip_str):
    ip_str = ip_str.strip()
    if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", ip_str):
        return ip_str
    return None

# ========================
# Cloudflare 节点测速类
# ========================
class CloudflareNodeTester:
    def __init__(self):
        self.nodes = []
        self.results = []
        self.lock = threading.Lock()

    def fetch_known_nodes(self):
        """香港常见 Cloudflare IP 段"""
        base_ranges = [
            "104.16.", "104.17.", "104.18.", "104.19."
        ]
        nodes = []
        for base_ip in base_ranges:
            for i in range(0, 20):  # 每段取 20 个 IP
                ip = f"{base_ip}{i}"
                nodes.append(ip)
        return nodes

    def test_node_speed(self, ip):
        """测试单个节点延迟"""
        try:
            start = time.time()
            sock = socket.create_connection((ip, TEST_PORT), timeout=TEST_TIMEOUT)
            sock.close()
            latency = (time.time() - start) * 1000
            with self.lock:
                self.results.append((ip, latency))
        except Exception:
            pass

    def worker(self, q):
        while True:
            ip = q.get()
            if ip is None:
                break
            self.test_node_speed(ip)
            q.task_done()

    def test_all_nodes(self):
        """启动多线程测速"""
        q = queue.Queue()
        for ip in self.nodes:
            q.put(ip)

        threads = []
        for _ in range(MAX_THREADS):
            t = threading.Thread(target=self.worker, args=(q,))
            t.start()
            threads.append(t)

        q.join()

        for _ in threads:
            q.put(None)
        for t in threads:
            t.join()

    def sort_and_display_results(self):
        """排序并显示结果"""
        sorted_results = sorted(self.results, key=lambda x: x[1])[:TOP_NODES]

        hk_results = []
        for ip, latency in sorted_results:
            country = get_ip_country(ip)
            if "香港" in country or country == "Hong Kong":
                hk_results.append((ip, latency, country))

        if not hk_results:
            print("⚠️ 未检测到香港节点，保存全部测速结果。")
            hk_results = [(ip, latency, get_ip_country(ip)) for ip, latency in sorted_results]

        print("\n🏁 最快节点（香港）:")
        for ip, latency, country in hk_results:
            print(f"{ip:<15} {latency:.2f} ms  {country}")

        self.save_results(hk_results)

    def save_results(self, results):
        """保存结果到文件"""
        with open(TXT_OUTPUT_FILE, "w", encoding="utf-8") as f:
            for ip, latency, country in results:
                f.write(f"{ip}#hk {country} HK\n")

        print(f"\n✅ 已保存结果到 {TXT_OUTPUT_FILE}")

    def run(self):
        print("🚀 正在获取 Cloudflare 节点...")
        self.nodes = self.fetch_known_nodes()
        print(f"共获取 {len(self.nodes)} 个节点，开始测速...\n")

        self.test_all_nodes()
        self.sort_and_display_results()

# ========================
# 主程序入口
# ========================
if __name__ == "__main__":
    tester = CloudflareNodeTester()
    tester.run()
