"""Built-in smart-contract templates for the template library.

Each template is a complete, sandbox-valid contract written against the
contract API (``state``, ``msg``, ``emit``, ``require``, ``transfer``,
``balance_of``).  They are exposed on the template-library page and can be
deployed with one click.
"""

TEMPLATES = [
    {
        "name": "token",
        "title": "可替代代币 (ERC-20 风格)",
        "category": "金融",
        "description": "发行一种可转账的代币，包含铸造、转账、余额查询与总量查询。",
        "constructor": [
            {"name": "name", "type": "string", "desc": "代币名称"},
            {"name": "symbol", "type": "string", "desc": "代币符号"},
            {"name": "supply", "type": "int", "desc": "初始发行量"},
        ],
        "functions": [
            {"name": "transfer", "desc": "向指定地址转账", "params": ["to", "amount"]},
            {"name": "balance_of", "desc": "查询某地址余额", "params": ["addr"]},
            {"name": "total_supply", "desc": "查询代币总量", "params": []},
        ],
        "source": '''# 可替代代币模板 (ERC-20 风格)
def init(name, symbol, supply):
    require(state.get("name") is None, "合约已初始化")
    state["name"] = name
    state["symbol"] = symbol
    state["total_supply"] = supply
    state["bal_" + msg.sender] = supply
    emit("Minted", to=msg.sender, amount=supply)

def transfer(to, amount):
    amount = int(amount)
    require(amount > 0, "转账金额必须为正")
    bal = state.get("bal_" + msg.sender, 0)
    require(bal >= amount, "余额不足")
    state["bal_" + msg.sender] = bal - amount
    state["bal_" + to] = state.get("bal_" + to, 0) + amount
    emit("Transfer", frm=msg.sender, to=to, amount=amount)

def balance_of(addr):
    return state.get("bal_" + addr, 0)

def total_supply():
    return state.get("total_supply", 0)
''',
    },
    {
        "name": "kv_store",
        "title": "键值存储",
        "category": "存储",
        "description": "一个简单的持久化键值对存储，支持写入与读取。",
        "constructor": [],
        "functions": [
            {"name": "set", "desc": "写入键值", "params": ["key", "value"]},
            {"name": "get", "desc": "读取键值", "params": ["key"]},
        ],
        "source": '''# 键值存储模板
def init():
    state["owner"] = msg.sender
    state["count"] = 0
    emit("Initialized", owner=msg.sender)

def set(key, value):
    key = str(key)
    require(key != "", "键不能为空")
    state[key] = value
    state["count"] = state.get("count", 0) + 1
    emit("Set", key=key, value=value, by=msg.sender)

def get(key):
    return state.get(str(key), None)
''',
    },
    {
        "name": "voting",
        "title": "投票合约",
        "category": "治理",
        "description": "创建候选人、投票、查看票数。每个地址限投一次。",
        "constructor": [
            {"name": "candidates", "type": "list", "desc": "候选人列表，如 ['Alice','Bob']"},
        ],
        "functions": [
            {"name": "vote", "desc": "给候选人投票", "params": ["candidate"]},
            {"name": "tally", "desc": "查询候选人票数", "params": ["candidate"]},
        ],
        "source": '''# 投票合约模板
def init(candidates):
    require(state.get("owner") is None, "已初始化")
    state["owner"] = msg.sender
    state["candidates"] = list(candidates)
    for c in candidates:
        state["vote_" + str(c)] = 0
    emit("Created", candidates=candidates)

def vote(candidate):
    require(str(candidate) in state.get("candidates", []), "候选人不存在")
    require(state.get("voted_" + msg.sender, False) is False, "已投过票")
    state["voted_" + msg.sender] = True
    state["vote_" + str(candidate)] = state.get("vote_" + str(candidate), 0) + 1
    emit("Voted", voter=msg.sender, candidate=str(candidate))

def tally(candidate):
    return state.get("vote_" + str(candidate), 0)
''',
    },
    {
        "name": "escrow",
        "title": "托管合约",
        "category": "金融",
        "description": "买家存入资金，买家确认后资金释放给卖家，买家可申请退款。",
        "constructor": [
            {"name": "seller", "type": "address", "desc": "卖家地址"},
        ],
        "functions": [
            {"name": "deposit", "desc": "买家存入资金", "params": []},
            {"name": "release", "desc": "买家确认放款给卖家", "params": []},
            {"name": "refund", "desc": "买家申请退款", "params": []},
            {"name": "amount", "desc": "查询托管金额", "params": []},
        ],
        "source": '''# 托管合约模板
def init(seller):
    require(state.get("seller") is None, "已初始化")
    state["seller"] = seller
    state["buyer"] = msg.sender
    state["amount"] = 0
    state["released"] = False
    emit("Created", seller=seller, buyer=msg.sender)

def deposit():
    require(msg.sender == state["buyer"], "只有买家可存入")
    require(state["released"] is False, "合约已结束")
    state["amount"] = state.get("amount", 0) + msg.value
    emit("Deposited", by=msg.sender, amount=msg.value)

def release():
    require(msg.sender == state["buyer"], "只有买家可确认放款")
    require(state["released"] is False, "已放款")
    state["released"] = True
    transfer(state["seller"], state["amount"])
    emit("Released", seller=state["seller"], amount=state["amount"])

def refund():
    require(msg.sender == state["buyer"], "只有买家可退款")
    require(state["released"] is False, "已放款")
    state["released"] = True
    transfer(state["buyer"], state["amount"])
    emit("Refunded", buyer=state["buyer"], amount=state["amount"])

def amount():
    return state.get("amount", 0)
''',
    },
    {
        "name": "auction",
        "title": "拍卖合约",
        "category": "金融",
        "description": "英式拍卖：出价必须高于当前最高价，拍卖结束后最高出价者胜出。",
        "constructor": [
            {"name": "item", "type": "string", "desc": "拍卖品名称"},
            {"name": "starting_price", "type": "int", "desc": "起拍价"},
            {"name": "end_height", "type": "int", "desc": "结束区块高度"},
        ],
        "functions": [
            {"name": "bid", "desc": "出价（需附带 value）", "params": []},
            {"name": "highest_bidder", "desc": "查询最高出价者", "params": []},
            {"name": "highest_bid", "desc": "查询最高出价", "params": []},
        ],
        "source": '''# 拍卖合约模板
def init(item, starting_price, end_height):
    require(state.get("item") is None, "已初始化")
    state["item"] = item
    state["highest_bid"] = int(starting_price)
    state["highest_bidder"] = msg.sender
    state["end_height"] = int(end_height)
    state["ended"] = False
    emit("AuctionCreated", item=item, start=int(starting_price))

def bid():
    require(block_height < state["end_height"], "拍卖已结束")
    require(msg.value > state["highest_bid"], "出价必须高于当前最高价")
    prev_bidder = state["highest_bidder"]
    prev_bid = state["highest_bid"]
    # 退回上一出价人
    transfer(prev_bidder, prev_bid)
    state["highest_bid"] = msg.value
    state["highest_bidder"] = msg.sender
    emit("Bid", bidder=msg.sender, amount=msg.value)

def highest_bidder():
    return state["highest_bidder"]

def highest_bid():
    return state["highest_bid"]
''',
    },
    {
        "name": "crowdfunding",
        "title": "众筹合约",
        "category": "金融",
        "description": "众筹目标金额，支持出资与查询进度，达到目标后项目方可提现。",
        "constructor": [
            {"name": "goal", "type": "int", "desc": "众筹目标金额"},
        ],
        "functions": [
            {"name": "contribute", "desc": "出资（需附带 value）", "params": []},
            {"name": "progress", "desc": "查询已筹金额", "params": []},
            {"name": "withdraw", "desc": "项目方提现（需达到目标）", "params": []},
        ],
        "source": '''# 众筹合约模板
def init(goal):
    require(state.get("owner") is None, "已初始化")
    state["owner"] = msg.sender
    state["goal"] = int(goal)
    state["raised"] = 0
    state["withdrawn"] = False
    emit("CampaignStarted", goal=int(goal))

def contribute():
    require(state["withdrawn"] is False, "众筹已结束")
    state["raised"] = state.get("raised", 0) + msg.value
    state["contrib_" + msg.sender] = state.get("contrib_" + msg.sender, 0) + msg.value
    emit("Contribution", from_=msg.sender, amount=msg.value)

def progress():
    return state.get("raised", 0)

def withdraw():
    require(msg.sender == state["owner"], "只有项目方可提现")
    require(state["raised"] >= state["goal"], "未达到众筹目标")
    require(state["withdrawn"] is False, "已提现")
    state["withdrawn"] = True
    transfer(state["owner"], state["raised"])
    emit("Withdrawn", amount=state["raised"])
''',
    },
    {
        "name": "merkle_claim",
        "title": "代币空投领取（资格证明 / 期限 / 回收）",
        "category": "金融",
        "description": "项目方按白名单预存一批固定数量代币；名单内地址凭 Merkle 资格证明各领一次，设有截止高度，过期后项目方可一次性收回剩余代币。",
        "constructor": [
            {"name": "merkle_root", "type": "string", "desc": "白名单 Merkle 根（64位十六进制，由领取页面生成）"},
            {"name": "amount_each", "type": "int", "desc": "每个合格地址可领取的固定数量"},
            {"name": "total_slots", "type": "int", "desc": "白名单地址总数（决定代币总盘子）"},
            {"name": "end_height", "type": "int", "desc": "领取截止高度（该高度之后不可再领）"},
        ],
        "functions": [
            {"name": "claim", "desc": "凭 Merkle 资格证明领取固定数量代币", "params": ["proof"]},
            {"name": "recover_remaining", "desc": "截止后项目方一次性收回剩余代币", "params": []},
            {"name": "deposit", "desc": "向合约补充代币（附带 value 调用）", "params": []},
            {"name": "info", "desc": "查询领取概况（根/单份/已领/剩余/截止高度等）", "params": []},
            {"name": "has_claimed", "desc": "查询某地址是否已领取", "params": ["addr"]},
        ],
        "source": '''# 代币空投领取合约
# 白名单地址的叶子 = sha256_hex(地址字符串)；proof 为 ["L"|"R", 兄弟节点哈希] 列表。
def init(merkle_root, amount_each, total_slots, end_height):
    require(state.get("owner") is None, "合约已初始化")
    merkle_root = str(merkle_root)
    require(len(merkle_root) == 64, "Merkle 根必须是 64 位十六进制")
    amount_each = int(amount_each)
    total_slots = int(total_slots)
    end_height = int(end_height)
    require(amount_each > 0, "单地址领取数量必须为正")
    require(total_slots > 0, "白名单数量必须为正")
    require(end_height > block_height, "截止高度必须在未来")
    state["owner"] = msg.sender
    state["merkle_root"] = merkle_root
    state["amount_each"] = amount_each
    state["total_slots"] = total_slots
    state["end_height"] = end_height
    state["claimed_count"] = 0
    state["recovered"] = False
    emit("ClaimCampaignCreated", owner=msg.sender, root=merkle_root,
         amount_each=amount_each, total_slots=total_slots,
         total_amount=amount_each * total_slots, end_height=end_height)

def deposit():
    require(state.get("recovered", False) is False, "活动已结束并回收")
    require(msg.value > 0, "存入金额必须为正")
    emit("Deposited", frm=msg.sender, amount=msg.value,
         balance=this_balance())

def claim(proof):
    require(block_height <= state["end_height"], "已过领取截止高度")
    require(state.get("recovered", False) is False, "剩余代币已被项目方回收")
    require(state.get("claimed_" + msg.sender, False) is False, "该地址已领取过")
    # 用资格证明重建 Merkle 根，与部署时公布的根比对
    node = sha256_hex(msg.sender)
    for step in proof:
        side = step[0]
        sibling = str(step[1])
        if side == "R":
            node = sha256_pair_hex(node, sibling)
        else:
            node = sha256_pair_hex(sibling, node)
    require(node == state["merkle_root"], "资格证明无效：地址不在白名单内")
    amount = state["amount_each"]
    require(this_balance() >= amount, "合约代币余额不足，请联系项目方充值")
    state["claimed_" + msg.sender] = True
    state["claimed_count"] = state.get("claimed_count", 0) + 1
    transfer(msg.sender, amount)
    emit("Claimed", to=msg.sender, amount=amount,
         height=block_height, claimed_count=state["claimed_count"])

def recover_remaining():
    require(msg.sender == state["owner"], "只有项目方可以回收")
    require(block_height > state["end_height"], "尚未到截止高度，不能回收")
    require(state.get("recovered", False) is False, "剩余代币已回收")
    remaining = this_balance()
    require(remaining > 0, "没有可回收的剩余代币")
    state["recovered"] = True
    transfer(state["owner"], remaining)
    emit("Recovered", owner=state["owner"], amount=remaining,
         claimed_count=state.get("claimed_count", 0), height=block_height)

def has_claimed(addr):
    return state.get("claimed_" + str(addr), False)

def info():
    claimed = state.get("claimed_count", 0)
    slots = state["total_slots"]
    return {
        "owner": state["owner"],
        "merkle_root": state["merkle_root"],
        "amount_each": state["amount_each"],
        "total_slots": slots,
        "total_amount": state["amount_each"] * slots,
        "claimed_count": claimed,
        "remaining_slots": slots - claimed,
        "end_height": state["end_height"],
        "current_height": block_height,
        "active": block_height <= state["end_height"],
        "recovered": state.get("recovered", False),
        "contract_balance": this_balance(),
    }
''',
    },
    {
        "name": "counter",
        "title": "计数器",
        "category": "基础",
        "description": "最简单的合约，演示状态持久化与事件。",
        "constructor": [],
        "functions": [
            {"name": "increment", "desc": "计数 +1", "params": []},
            {"name": "get", "desc": "查询当前计数", "params": []},
        ],
        "source": '''# 计数器模板
def init():
    state["count"] = 0
    emit("Created", by=msg.sender)

def increment():
    state["count"] = state.get("count", 0) + 1
    emit("Incremented", value=state["count"])

def get():
    return state.get("count", 0)
''',
    },
]


def get_templates():
    return TEMPLATES


def get_template(name):
    for t in TEMPLATES:
        if t["name"] == name:
            return t
    return None


def template_catalog():
    """Return templates without their source (for the list view)."""
    return [
        {
            "name": t["name"],
            "title": t["title"],
            "category": t["category"],
            "description": t["description"],
            "constructor": t["constructor"],
            "functions": t["functions"],
        }
        for t in TEMPLATES
    ]
