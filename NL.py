import socket
import threading
import queue
import time
import requests
import re

# ========================
# 配置参数
# ========================
TEST_TIMEOUT = 2
TEST_PORT = 443
MAX_THREADS = 50
TOP_NODES = 80
TXT_OUTPUT_FILE = "HK.txt"

# Cloudflare 香港常见网段
BASE_RANGES = [
    "104.28.193", "104.28.194", "104.28.195",
    "104.28.196", "104.28.197", "104.28.198", "104.28.199"
]

# ========================
# 节点测速类
# ========================
class CloudflareNodeTester:
    def __init__(self):
        self.nodes = []
        self.results = []
        self.lock = threading.Lock()

    def fetch_known_nodes(self):
        nodes = []
        for base in BASE_RANGES:
            for i in range(1, 50):  # 每个网段生成 49 个 IP
                nodes.append(f"{base}.{i}")
        self.nodes = nodes

    def test_node_speed(self, ip):
        """测速 + 获取 colo"""
        try:
            start = time.time()
            # TCP 测试端口连通性
            sock = socket.create_connection((ip, TEST_PORT), timeout=TEST_TIMEOUT)
            sock.close()
            latency = (time.time() - start) * 1000

            # 请求 /cdn-cgi/trace 获取 colo
            try:
                r = requests.get(f"https://{ip}/cdn-cgi/trace", timeout=TEST_TIMEOUT, verify=False)
                m = re.search(r"colo=(\w+)", r.text)
                colo = m.group(1) if m else "未知"
            except Exception:
                colo = "未知"

            with self.lock:
                self.results.append((ip, latency, colo))
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

    def run(self):
        print("🚀 正在生成 Cloudflare 节点列表...")
        self.fetch_known_nodes()
        print(f"共生成 {len(self.nodes)} 个节点，开始测速...\n")

        start_time = time.time()
        self.test_all_nodes()

        if not self.results:
            print("❌ 无可用节点。")
            return

        # 只保留 colo=HKG
        hk_nodes = [r for r in self.results if r[2] == "HKG"]
        if not hk_nodes:
            print("⚠️ 未检测到香港节点，保存所有节点。")
            hk_nodes = self.results

        # 按延迟排序
        hk_nodes.sort(key=lambda x: x[1])

        # 打印结果
        print("\n🏁 最快节点（香港）:")
        for ip, latency, colo in hk_nodes[:TOP_NODES]:
            print(f"{ip:<15} {latency:.2f} ms  {colo}")

        # 保存到 HK.txt
        with open(TXT_OUTPUT_FILE, "w", encoding="utf-8") as f:
            for ip, latency, colo in hk_nodes:
                f.write(f"{ip}:443#hk HKG {latency:.2f}ms\n")

        print(f"\n✅ 已保存 {len(hk_nodes)} 条香港节点到 {TXT_OUTPUT_FILE}")
        print(f"⏱️ 总耗时：{time.time() - start_time:.1f} 秒")


# ========================
# 主程序
# ========================
if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    tester = CloudflareNodeTester()
    tester.run()
