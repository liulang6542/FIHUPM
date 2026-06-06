import sys
from collections import defaultdict
import heapq, math, os, time, psutil, gc

sys.setrecursionlimit(10000)

K = 21   #K_LOWER
K_UPPER = K + 1

DB_PATH = r"C:\Users\lx\pythonProject5\对比算法2025\bms2.txt"
PROFIT_PATH = r"C:\Users\lx\pythonProject5\对比算法2025\bmsf2profit.txt"
INSERTION_RATE = 0.2
NUM_INCREMENTS = 9

assert K >= 1 and K_UPPER > K


class PerformanceMonitor:
    def __init__(self):
        self.process = psutil.Process(os.getpid())
        self.stage_stats = []

    def start_stage(self, stage_name):
        return {
            "name": stage_name,
            "start_time": time.time(),
            "start_memory": self.get_memory_usage(),
        }

    def end_stage(self, stage_info):
        end_time = time.time()
        end_memory = self.get_memory_usage()
        stage_info["end_time"] = end_time
        stage_info["end_memory"] = end_memory
        stage_info["duration"] = end_time - stage_info["start_time"]
        stage_info["memory_delta"] = end_memory - stage_info["start_memory"]
        self.stage_stats.append(stage_info)
        return stage_info

    def get_memory_usage(self):
        try:
            return self.process.memory_info().rss / 1024 / 1024
        except Exception:
            return 0.0

    def print_stage_performance(self, stage_info):
        print(f"   运行时间：{stage_info['duration']:.4f} 秒")
        print(f"   内存使用：{stage_info['end_memory']:.2f} MB")
        print(f"   内存变化：{stage_info['memory_delta']:+.2f} MB")

    def print_final_summary(self):
        if not self.stage_stats:
            return
        header("性能统计汇总")
        print(
            "阶段名称".ljust(25) + " | " + "运行时间(秒)".rjust(12)
            + " | " + "内存使用(MB)".rjust(12) + " | " + "内存变化(MB)".rjust(12)
        )
        print("-" * 70)
        total_time = 0
        max_memory = 0
        for stage in self.stage_stats:
            total_time += stage["duration"]
            max_memory = max(max_memory, stage["end_memory"])
            mem_str = f"{stage['memory_delta']:+.2f}"
            print(
                f"{stage['name'][:24].ljust(25)} | "
                f"{stage['duration']:>12.4f} | "
                f"{stage['end_memory']:>12.2f} | "
                f"{mem_str:>12}"
            )
        print("-" * 70)
        print(f"{'总计'.ljust(25)} | {total_time:>12.4f} | {max_memory:>12.2f} | {'峰值内存':>12}")
        print(f"\n   峰值内存：{max_memory:.2f} MB")
        print(f"   平均每阶段时间：{total_time / len(self.stage_stats):.4f} 秒")
        print(f"   处理了 {len(self.stage_stats)} 个阶段")


def header(title):
    print("\n" + "=" * 12 + f" {title} " + "=" * 12)


def parse_trans(s):
    return [(int(a), int(b)) for a, b in (p.split(",") for p in s.strip().split())]


def load(db_path, profit_path):
    with open(db_path, encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()]
    uu = {}
    with open(profit_path, encoding="utf-8") as f:
        for l in f:
            if l.strip():
                a, b = l.strip().split(",")
                uu[int(a)] = float(b)
    return [parse_trans(l) for l in lines], uu


def split_data(transactions, rate, n_inc):
    total = len(transactions)
    orig_n = int(total * (1 - rate))
    rest = transactions[orig_n:]
    sz = math.ceil(len(rest) / n_inc) if n_inc > 0 else len(rest)
    batches = [rest[i * sz:(i + 1) * sz] for i in range(n_inc) if rest[i * sz:(i + 1) * sz]]
    print(f"总事务数：{total}，原始：{orig_n}，增量批次：{len(batches)}")
    return transactions[:orig_n], batches


class E:
    __slots__ = ("tid", "u", "ru")

    def __init__(self, tid, u, ru=0.0):
        self.tid = tid
        self.u = float(u)
        self.ru = float(ru)


def scan(transactions, start_tid, uu, GUL, GTWU, TWUMap=None):
    tid = start_tid
    for t in transactions:
        tu = sum(uu.get(i, 0.0) * q for i, q in t)
        if tu == 0:
            tid += 1
            continue
        present = {i: uu.get(i, 0.0) * q for i, q in t if uu.get(i, 0.0) * q != 0}
        if not present:
            tid += 1
            continue
        for i, u in present.items():
            GUL.setdefault(i, []).append(E(tid, u))
            GTWU[i] = GTWU.get(i, 0.0) + tu
            if TWUMap is not None:
                TWUMap[i] = TWUMap.get(i, 0.0) + tu
        tid += 1
    return tid


def get_order(GTWU):
    return [it for it, _ in sorted(GTWU.items(), key=lambda x: (x[1], x[0]))]


def reconstruct_ru(promising, GUL, order):
    RUA = defaultdict(float)
    for it in reversed(order):
        if it not in promising:
            continue
        for e in GUL[it]:
            e.ru = RUA[e.tid]
        for e in GUL[it]:
            RUA[e.tid] += e.u


def join_uls(ulA, ulB, pfx_map):
    i = j = 0
    out = []
    while i < len(ulA) and j < len(ulB):
        a, b = ulA[i], ulB[j]
        if a.tid == b.tid:
            u = a.u + b.u - (pfx_map.get(a.tid, 0.0) if pfx_map is not None else 0.0)
            if u > 0 or b.ru > 0:
                out.append(E(a.tid, u, b.ru))
            i += 1
            j += 1
        elif a.tid < b.tid:
            i += 1
        else:
            j += 1
    return out


def to_map(ul):
    return {e.tid: e.u for e in ul}


class MinHeap:
    def __init__(self, cap):
        self.cap = cap
        self.h = []
        self.ks = set()

    def __len__(self):
        return len(self.h)

    def add(self, items, u):
        key = frozenset(items)
        if not key:
            return False
        u = float(u)
        if key in self.ks:
            for idx, (old_u, old_key) in enumerate(self.h):
                if old_key == key:
                    if u > old_u:
                        self.h[idx] = (u, key)
                        heapq.heapify(self.h)
                        return True
                    return False
            return False
        if len(self.h) < self.cap:
            heapq.heappush(self.h, (u, key))
            self.ks.add(key)
            return True
        if u > self.h[0][0]:
            _, old = heapq.heapreplace(self.h, (u, key))
            self.ks.discard(old)
            self.ks.add(key)
            return True
        return False

    def min_u(self):
        if len(self.h) < self.cap:
            return 0.0
        return self.h[0][0] if self.h else 0.0

    def kth_u(self, k):
        if len(self.h) < k:
            return 0.0
        arr = heapq.nlargest(k, self.h, key=lambda x: x[0])
        return arr[-1][0]

    def all_desc(self):
        return sorted(((u, tuple(sorted(s))) for u, s in self.h), key=lambda x: -x[0])


def explore(prefix, pfx_map, ext_list, pq, minU):
    for idx in range(len(ext_list)):
        it, ul = ext_list[idx]
        u_x = sum(e.u for e in ul)
        ru_x = sum(e.ru for e in ul)
        if u_x >= minU:
            pq.add(prefix + (it,), u_x)
            minU = pq.min_u()
        if u_x + ru_x < minU:
            continue
        cur_map = to_map(ul)
        tail = []
        for jt, ulJ in ext_list[idx + 1:]:
            jnd = join_uls(ul, ulJ, pfx_map)
            if jnd:
                tail.append((jt, jnd))
        if tail:
            minU = explore(prefix + (it,), cur_map, tail, pq, minU)
    return minU


def mine_once(GUL, order, GTWU, k_upper, minU):
    promising = {it for it in order if GTWU.get(it, 0.0) >= minU and it in GUL and GUL[it]}
    reconstruct_ru(promising, GUL, order)

    ext = []
    for it in order:
        if it not in promising:
            continue
        ul = GUL[it]
        if sum(e.u for e in ul) + sum(e.ru for e in ul) >= minU:
            ext.append((it, ul))

    pq = MinHeap(k_upper)
    for it, ul in ext:
        u = sum(e.u for e in ul)
        if u >= minU:
            pq.add((it,), u)

    search_minU = minU if len(pq) >= k_upper else 0.0
    explore((), None, ext, pq, search_minU)
    return pq


def mine(GUL, order, GTWU, k_upper, prev_minUlower=None):
    singles = sorted(
        [sum(e.u for e in GUL[i]) for i in order if i in GUL and GUL[i]],
        reverse=True,
    )

    s1 = singles[k_upper - 1] if len(singles) >= k_upper else 0.0
    hint = prev_minUlower if prev_minUlower is not None else 0.0
    init_minU = max(s1, hint)

    pq = mine_once(GUL, order, GTWU, k_upper, init_minU)

    if len(pq) < k_upper and init_minU > 0:
        pq = mine_once(GUL, order, GTWU, k_upper, 0.0)

    return pq


class ITree:
    def __init__(self):
        self.patterns = {}
        self.inv = defaultdict(set)

    def insert(self, items, u):
        key = frozenset(items)
        self.patterns[key] = float(u)
        for it in key:
            self.inv[it].add(key)

    def update(self, transactions, uu):
        for t in transactions:
            present = {i: uu.get(i, 0.0) * q for i, q in t if uu.get(i, 0.0) * q != 0}
            if not present:
                continue
            t_set = set(present)
            visited = set()
            for i in t_set:
                for key in self.inv.get(i, set()):
                    if key in visited:
                        continue
                    visited.add(key)
                    if key.issubset(t_set):
                        self.patterns[key] += sum(present[x] for x in key)

    def top_k(self, k):
        return sorted(
            ((tuple(sorted(ks)), u) for ks, u in self.patterns.items()),
            key=lambda x: -x[1],
        )[:k]

    def clear(self):
        self.patterns.clear()
        self.inv.clear()


def rebuild_tree(pq, tree):
    tree.clear()
    for u, items in pq.all_desc():
        tree.insert(items, u)


def main():
    monitor = PerformanceMonitor()
    program_start = monitor.start_stage("程序总体运行")

    all_trans, uu = load(DB_PATH, PROFIT_PATH)
    orig, batches = split_data(all_trans, INSERTION_RATE, NUM_INCREMENTS)

    GUL = {}
    GTWU = {}
    tree = ITree()

    stage1 = monitor.start_stage("阶段1（原始挖掘）")
    tid = scan(orig, 1, uu, GUL, GTWU)
    order = get_order(GTWU)
    pq = mine(GUL, order, GTWU, K_UPPER)
    rebuild_tree(pq, tree)
    prev_minUupper = pq.kth_u(K)
    prev_minUlower = pq.min_u()
    print(f"[原始库] K={K}  K_UPPER={K_UPPER}  minUupper={prev_minUupper:.4f}  minUlower={prev_minUlower:.4f}")
    print(f"原始挖掘完成。top-{K} 数量：{len(tree.top_k(K))}")
    monitor.end_stage(stage1)
    monitor.print_stage_performance(stage1)

    for bidx, inc in enumerate(batches, 1):
        stage = monitor.start_stage(f"阶段{bidx + 1}（增量批次{bidx}）")
        header(f"增量批次 {bidx}")

        TWUMap = {}
        tid = scan(inc, tid, uu, GUL, GTWU, TWUMap)
        max_twu_id = max(TWUMap.values()) if TWUMap else 0.0
        gap = max(prev_minUupper - prev_minUlower, 0.0)

        if max_twu_id > gap or len(tree.patterns) < K:
            header(f"增量批次 {bidx}：触发重挖")
            print(f"   max_TWU(ID)={max_twu_id:.4f}  gap={gap:.4f}")
            order = get_order(GTWU)
            pq = mine(GUL, order, GTWU, K_UPPER, prev_minUlower)
            rebuild_tree(pq, tree)
            prev_minUupper = pq.kth_u(K)
            prev_minUlower = pq.min_u()
        else:
            print(f"   无需重挖：更新 itemset-tree  max_TWU(ID)={max_twu_id:.4f} <= gap={gap:.4f}")
            tree.update(inc, uu)

        top = tree.top_k(K)
        print(f"当前 top-{K} 数量：{len(top)}")
        monitor.end_stage(stage)
        monitor.print_stage_performance(stage)
        gc.collect()

    header("最终挖掘结果汇总")
    final_top = tree.top_k(K)
    print(f"最终 top-{K} 项集数量：{len(final_top)}")
    print(f"最终高效用项集（仅项集）：")
    for items, u in final_top:
        print("{" + ", ".join(map(str, items)) + "}")

    monitor.end_stage(program_start)
    monitor.print_final_summary()


if __name__ == "__main__":
    main()
