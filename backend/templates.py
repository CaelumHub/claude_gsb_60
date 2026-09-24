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
        "name": "merkle_airdrop",
        "title": "代币领取（资格证明空投）",
        "category": "金融",
        "description": "项目方把白名单的默克尔根与每份固定数量、截止高度写入合约并注入代币；"
                       "名单内地址凭资格证明在截止高度前各领一份（仅限一次），"
                       "每次领取都记录事件；截止后项目方可一次性回收剩余代币。",
        "constructor": [
            {"name": "merkle_root", "type": "string",
             "desc": "资格名单的默克尔根（由地址列表生成，可在代币领取页计算）"},
            {"name": "claim_amount", "type": "int", "desc": "每个地址可领取的固定数量"},
            {"name": "deadline", "type": "int", "desc": "领取截止的区块高度（含该高度）"},
        ],
        "functions": [
            {"name": "fund", "desc": "项目方注入待发放代币（需附带 value）", "params": []},
            {"name": "claim", "desc": "凭资格证明领取固定数量（每地址限一次）", "params": ["proof"]},
            {"name": "reclaim", "desc": "截止后项目方一次性回收剩余代币", "params": []},
            {"name": "stats", "desc": "查询已领/剩余/截止高度等进度", "params": []},
            {"name": "has_claimed", "desc": "查询某地址是否已领取", "params": ["addr"]},
            {"name": "verify", "desc": "校验某地址的资格证明是否有效", "params": ["address", "proof"]},
        ],
        "source": '''# 代币领取模板（默克尔资格证明 + 截止高度 + 过期回收）
# 哈希方案（与后端 backend/airdrop.py 完全一致）：
#   叶子 = sha256(地址小写)；父节点 = sha256(左子 || 右子)
# 部署后项目方需先调用 fund() 并附带 value，注入待发放的代币池。

def init(merkle_root, claim_amount, deadline):
    require(state.get("owner") is None, "已初始化")
    require(int(claim_amount) > 0, "每份数量必须为正")
    require(int(deadline) > 0, "截止高度必须为正")
    state["owner"] = msg.sender
    state["merkle_root"] = str(merkle_root)
    state["claim_amount"] = int(claim_amount)
    state["deadline"] = int(deadline)
    state["claimed_count"] = 0
    state["total_claimed"] = 0
    state["reclaimed"] = False
    emit("AirdropCreated", owner=msg.sender, merkle_root=str(merkle_root),
         claim_amount=int(claim_amount), deadline=int(deadline))

def _leaf_root(address, proof):
    # 从叶子（地址哈希）沿证明路径折叠，返回计算出的根。
    node = sha256_hex(address)
    for step in proof:
        require(step["dir"] in ("L", "R"), "证明中的方向非法")
        sib = step["hash"]
        if step["dir"] == "R":
            node = sha256_hex(bytes.fromhex(node) + bytes.fromhex(sib))
        else:
            node = sha256_hex(bytes.fromhex(sib) + bytes.fromhex(node))
    return node

def fund():
    require(msg.value > 0, "注入金额必须为正")
    emit("Funded", frm=msg.sender, amount=msg.value, balance=this_balance())

def claim(proof):
    require(state.get("reclaimed") is False, "活动已结束并被回收")
    require(block_height <= state["deadline"], "已过截止高度，领取关闭")
    require(state.get("claimed_" + msg.sender, False) is False,
            "该地址已领取过，不能重复领取")
    require(len(proof) <= 64, "证明路径过长")
    require(_leaf_root(msg.sender, proof) == state["merkle_root"],
            "资格证明无效：地址不在名单或证明错误")
    amount = state["claim_amount"]
    require(this_balance() >= amount, "合约余额不足，请联系项目方注入代币")
    state["claimed_" + msg.sender] = True
    state["claimed_count"] = state["claimed_count"] + 1
    state["total_claimed"] = state["total_claimed"] + amount
    transfer(msg.sender, amount)
    emit("Claimed", address=msg.sender, amount=amount,
         height=block_height, seq=state["claimed_count"])

def reclaim():
    require(msg.sender == state["owner"], "只有项目方可回收")
    require(block_height > state["deadline"], "未到截止高度，暂不能回收")
    require(state["reclaimed"] is False, "已回收过，不能重复回收")
    state["reclaimed"] = True
    remaining = this_balance()
    if remaining > 0:
        transfer(state["owner"], remaining)
    emit("Reclaimed", owner=state["owner"], amount=remaining,
         height=block_height)

def stats():
    return {
        "owner": state["owner"],
        "merkle_root": state["merkle_root"],
        "claim_amount": state["claim_amount"],
        "deadline": state["deadline"],
        "current_height": block_height,
        "open": block_height <= state["deadline"]
                and state["reclaimed"] is False,
        "claimed_count": state["claimed_count"],
        "total_claimed": state["total_claimed"],
        "remaining": this_balance(),
        "reclaimed": state["reclaimed"],
    }

def has_claimed(addr):
    return state.get("claimed_" + str(addr), False)

def verify(address, proof):
    try:
        return _leaf_root(str(address), proof) == state["merkle_root"]
    except:
        return False
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
