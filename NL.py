import socket
import threading
import queue
import time
import re
import requests

# ========================
# 参数配置
# ========================
TEST_TIMEOUT = 2          # 单个节点超时时间（秒）
TEST_PORT = 443           # 测试端口
MAX_THREADS = 50          # 并发线程数
TOP_NODES = 60            # 取前 60 个节点进行国家检测
TXT_OUTPUT_FILE = "HK.txt"  # 输出文件名

# ========================
# 国家映射
# ========================
COUNTRY_CODES = {
    "HK": "中国香港",
    "JP": "日本",
    "US": "美国",
    "SG": "新加坡",
    "TW": "台湾",
    "KR": "韩国",
    "GB": "英国",
    "DE": "德国",
    "FR": "法国",
    "CN": "中国大陆",
}

# ========================
# IP 查询函数（快速）
# ========================
def get_ip_country(ip):
    try:
        r = requests.get(f"https://ipinfo.io/{ip}/json", timeout=2)
        data = r.json()
        country = data.get("country", "")
        return COUNTRY_CODES.get(country, country or "未知")
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
        """仅取常见 Cloudflare 香港段"""
        base_ranges = [
            "104.16", "104.17", "104.18",
            "172.64", "172.65",
            "188.114"
        ]
        nodes = []
        for base in base_ranges:
            for i in range(0, 4):       # C 段
                for j in range(1, 26):  # D 段
                    ip = f"{base}.{i}.{j}"
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
        """多线程测速"""
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

    def quick_filter(self):
        """只保留延迟最低的前 N 个节点"""
        return sorted(self.results, key=lambda x: x[1])[:TOP_NODES]

    def run(self):
        print("🚀 正在获取 Cloudflare 节点...")
        self.nodes = self.fetch_known_nodes()
        print(f"共获取 {len(self.nodes)} 个节点，开始测速...\n")

        start_time = time.time()
        self.test_all_nodes()
        if not self.results:
            print("❌ 无可用节点。")
            return

        fast_nodes = self.quick_filter()
        print(f"📊 选出延迟最低的 {len(fast_nodes)} 个节点，开始查询地理位置...\n")

        display_list = []
        for ip, latency in fast_nodes:
            country = get_ip_country(ip)
            display_list.append((ip, latency, country))

        hk_list = [r for r in display_list if "香港" in r[2] or "Hong Kong" in r[2]]
        if not hk_list:
            print("⚠️ 未检测到香港节点，保存所有节点。")
            hk_list = display_list

        # 打印结果
        print("\n🏁 最快节点（香港）:")
        for ip, latency, country in hk_list:
            print(f"{ip:<15} {latency:.2f} ms  {country}")

        # 保存文件
        with open(TXT_OUTPUT_FILE, "w", encoding="utf-8") as f:
            for ip, latency, country in hk_list:
                f.write(f"{ip}#hk {country} HK\n")

        end_time = time.time()
        print(f"\n✅ 已保存结果到 {TXT_OUTPUT_FILE}")
        print(f"⏱️ 总耗时：{end_time - start_time:.1f} 秒")

# ========================
# 主程序入口
# ========================
if __name__ == "__main__":
    tester = CloudflareNodeTester()
    tester.run()
