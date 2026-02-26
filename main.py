import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import re
import datetime
from datetime import timezone, timedelta
from collections import defaultdict
from keep_alive import keep_alive

# --- 1. 権限（Intents）の設定 ---
intents = discord.Intents.default()
intents.members = True 
intents.message_content = True 
intents.voice_states = True 

# --- 2. 設定 ---
LOG_CHANNEL_ID = 1475491103225417738
WELCOME_CHANNEL_ID = 1475484575114330162
TICKET_CATEGORY_ID = 1475853559399452752
VC_CREATOR_ID = 1475482867818827829

last_messages = defaultdict(list)
temp_channels = [] 
JST = timezone(timedelta(hours=+9))

# --- 3. UIクラス（役職・チケット） ---

class RoleButton(discord.ui.Button):
    def __init__(self, role: discord.Role, removable: bool = True):
        # custom_idにフラグ情報を埋め込む (roleid_removable)
        rem_int = 1 if removable else 0
        super().__init__(label=role.name, style=discord.ButtonStyle.primary, custom_id=f"role_{role.id}_{rem_int}")
    
    async def callback(self, it: discord.Interaction):
        data = self.custom_id.split("_")
        role_id = int(data[1])
        removable = data[2] == "1"
        
        role = it.guild.get_role(role_id)
        if not role: 
            return await it.response.send_message("「ごめんね、その役職は見つからなかったみたい…」", ephemeral=True)
        
        if role in it.user.roles:
            if removable:
                await it.user.remove_roles(role)
                await it.response.send_message(f"「役職『{role.name}』を外したよ！また付けたくなったら言ってね！」", ephemeral=True)
            else:
                await it.response.send_message(f"「キミはもう『{role.name}』の役職を持っているよ！一度手に入れたら、ボクからは外せない決まりなんだ。えへへ、大切にしてね！」", ephemeral=True)
        else:
            try:
                await it.user.add_roles(role)
                await it.response.send_message(f"「役職『{role.name}』を付けたよ！えへへ、よく似合ってるよ！」", ephemeral=True)
            except discord.Forbidden:
                await it.response.send_message("「ごめんね、ボクの権限が足りなくて役職を付けられなかったよ…」", ephemeral=True)

class RolePanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

class ConfirmCloseView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="本当に閉じる", style=discord.ButtonStyle.danger, custom_id="confirm_close")
    async def confirm_close(self, it: discord.Interaction, button: discord.ui.Button):
        await it.channel.delete()

class CloseTicketView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="チケットを閉じる", style=discord.ButtonStyle.secondary, emoji="🔒", custom_id="close_ticket")
    async def close_ticket(self, it: discord.Interaction, button: discord.ui.Button):
        await it.response.send_message("「このチケットを閉じても大丈夫かな？やり残したことはない？」", view=ConfirmCloseView(), ephemeral=True)

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    async def create_ticket_logic(self, it: discord.Interaction, ticket_type: str):
        await it.response.defer(ephemeral=True)
        guild, user = it.guild, it.user
        category = guild.get_channel(TICKET_CATEGORY_ID)
        
        if not category:
            return await it.followup.send("「ごめんね、チケットを作る場所（カテゴリー）が見つからなかったよ…」", ephemeral=True)

        try:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
                guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)
            }
            channel = await guild.create_text_channel(name=f"🎫｜{ticket_type}-{user.display_name}", overwrites=overwrites, category=category)
            await it.followup.send(f"「チケットを作ったよ！こっちでボクたちが待ってるね：{channel.mention}」", ephemeral=True)
            # 埋め込みなしに変更
            await channel.send(f"**【{ticket_type}窓口】**\n「{user.mention}さん、こんにちは！ボクに内容を教えてね。」", view=CloseTicketView())
        except Exception as e:
            await it.followup.send(f"「作成に失敗しちゃった…。権限を確認してくれるかな？：`{e}`」", ephemeral=True)

    @discord.ui.button(label="🚨 通報", style=discord.ButtonStyle.danger, custom_id="ticket_report")
    async def report(self, it: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket_logic(it, "通報")

    @discord.ui.button(label="❓ 質問", style=discord.ButtonStyle.primary, custom_id="ticket_question")
    async def question(self, it: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket_logic(it, "質問")

    @discord.ui.button(label="💡 提案", style=discord.ButtonStyle.success, custom_id="ticket_suggest")
    async def suggest(self, it: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket_logic(it, "提案")

# --- 4. Bot本体 ---
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='/', intents=intents)

    async def setup_hook(self):
        self.add_view(TicketView())
        self.add_view(CloseTicketView())
        self.add_view(ConfirmCloseView())
        self.add_view(RolePanelView())
        self.update_status.start()
        await self.tree.sync()

    @tasks.loop(seconds=60)
    async def update_status(self):
        ping = round(self.latency * 1000)
        game = discord.Game(f"通信速度: {ping}ms | ボク、元気だよ！")
        await self.change_presence(activity=game)

    @update_status.before_loop
    async def before_update_status(self):
        await self.wait_until_ready()

bot = MyBot()

# --- 5. イベント処理（挨拶・防衛などは以前と同様のため省略可ですが、整合性のために保持） ---
@bot.event
async def on_ready():
    print(f'ログイン完了: {bot.user.name}')

@bot.event
async def on_voice_state_update(member, before, after):
    if after.channel and after.channel.id == VC_CREATOR_ID:
        try:
            new_ch = await member.guild.create_voice_channel(name=f"🔊｜{member.display_name}の部屋", category=after.channel.category)
            await member.move_to(new_ch)
            temp_channels.append(new_ch.id)
        except: pass
    if before.channel and before.channel.id in temp_channels and len(before.channel.members) == 0:
        try:
            await before.channel.delete()
            temp_channels.remove(before.channel.id)
        except: pass

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild: return
    now_jst = datetime.datetime.now(JST)
    now_hour = now_jst.hour
    content = message.content

    if "おはよう" in content:
        if 6 <= now_hour < 11: await message.channel.send(f"「{message.author.mention}、おはよう！今日もいい一日になりそうだね！」")
        elif 11 <= now_hour < 18: await message.channel.send(f"「{message.author.mention}、おはよう…かな？今はもう『こんにちは』の時間だよ！えへへ、寝坊しちゃった？」")
        elif 19 <= now_hour or now_hour < 5: await message.channel.send(f"「わわっ、{message.author.mention}！今は夜だよ？『こんばんは』か『おやすみ』じゃないかな？」")
        elif 5 <= now_hour < 6: await message.channel.send(f"「{message.author.mention}、おはよう！すっごく早起きだね！ボクも目が覚めちゃった！」")
        return

    if "こんにちは" in content:
        if 11 <= now_hour < 18: await message.channel.send(f"「{message.author.mention}、こんにちは！お外はどんな感じ？」")
        elif 5 <= now_hour < 11: await message.channel.send(f"「{message.author.mention}、こんにちは！…にはちょっと早いかな？今は『おはよう』の時間だよ！」")
        else: await message.channel.send(f"「{message.author.mention}、こんにちは！…って、今はもう暗いよ？『こんばんは』の時間だね！」")
        return

    if "おやすみ" in content:
        if 20 <= now_hour or now_hour < 5: await message.channel.send(f"「{message.author.mention}、おやすみ！ゆっくり休んで、また明日も遊ぼうね！」")
        elif 11 <= now_hour < 16: await message.channel.send(f"「{message.author.mention}、おやすみ！お昼寝かな？ボクも一緒に寝ちゃおうかな…」")
        else: await message.channel.send(f"「{message.author.mention}、おやすみ！…って、まだ寝ちゃうの？ちょっと早い気がするけど、お疲れ様！」")
        return

    if len(message.mentions) >= 5:
        await message.delete()
        await message.channel.send(f"「わわっ！{message.author.mention}、そんなにたくさん呼んだらみんなびっくりしちゃうよ！大量メンションはやめてね」", delete_after=5)
        return
    
    u_id, now = message.author.id, datetime.datetime.now(JST)
    last_messages[u_id].append({"content": message.content, "time": now})
    last_messages[u_id] = [m for m in last_messages[u_id] if (now - m["time"]).total_seconds() < 5]
    if len(last_messages[u_id]) >= 3 and len(set(m["content"] for m in last_messages[u_id][-3:])) == 1:
        await message.delete()
        await message.channel.send(f"「{message.author.mention}、同じことを何度も送るのは控えてね。みんなと楽しくお話ししよう！」", delete_after=5)
        return

    extract = re.search(r"https://(?:ptb\.|canary\.)?discord\.com/channels/(\d+)/(\d+)/(\d+)", message.content)
    if extract:
        g, c, m = map(int, extract.groups())
        if message.guild.id == g:
            try:
                f_msg = await bot.get_channel(c).fetch_message(m)
                emb = discord.Embed(description=f_msg.content, color=discord.Color.light_grey(), timestamp=f_msg.created_at)
                emb.set_author(name=f_msg.author.display_name, icon_url=f_msg.author.display_avatar.url)
                await message.reply(embed=emb, mention_author=False)
            except: pass
    await bot.process_commands(message)

@bot.event
async def on_member_join(member):
    ch = bot.get_channel(WELCOME_CHANNEL_ID)
    if ch: await ch.send(f"「ボクはエフィリン！よろしくね、{member.mention}！\nこのサーバーへようこそ！」")

# --- 6. スラッシュコマンド ---

@bot.tree.command(name="role_setup", description="役職パネルを置くよ")
@app_commands.describe(removable="一度付けたら外せなくする場合は False にしてね")
@app_commands.checks.has_permissions(administrator=True)
async def role_setup(it: discord.Interaction, text: str, role1: discord.Role, removable: bool = True):
    view = RolePanelView()
    view.add_item(RoleButton(role1, removable))
    # 埋め込みなしのテキストで送信
    content = f"**{text}**\n「ボクが役職を配るよ！好きなボタンを押してね！」"
    await it.channel.send(content, view=view)
    await it.response.send_message("「役職パネルを置いたよ！これでバッチリだね！」", ephemeral=True)

@bot.tree.command(name="role_add", description="既存パネルにボタンを足すよ")
@app_commands.describe(removable="一度付けたら外せなくする場合は False にしてね")
@app_commands.checks.has_permissions(administrator=True)
async def role_add(it: discord.Interaction, message_id: str, role: discord.Role, removable: bool = True):
    await it.response.defer(ephemeral=True)
    try:
        msg = await it.channel.fetch_message(int(message_id))
        view = discord.ui.View.from_message(msg)
        view.timeout = None
        # 重複チェック
        for item in view.children:
            if isinstance(item, discord.ui.Button) and item.custom_id and item.custom_id.startswith(f"role_{role.id}"):
                return await it.followup.send("「その役職はもうパネルにあるよ！」", ephemeral=True)
        
        view.add_item(RoleButton(role, removable))
        await msg.edit(view=view)
        await it.followup.send(f"✅ 「『{role.name}』のボタンを足しておいたよ！(取り外し可能: {removable})」", ephemeral=True)
    except: await it.followup.send("「失敗しちゃった…。IDが合ってるか確認してくれるかな？」", ephemeral=True)

@bot.tree.command(name="ticket_setup", description="窓口を作るよ")
@app_commands.checks.has_permissions(administrator=True)
async def ticket_setup(it: discord.Interaction):
    # 埋め込みなし
    content = "**📩 お問い合わせ窓口**\n「困ったことがあったらボクたちに教えて！チケットを作るよ。」"
    await it.channel.send(content, view=TicketView())
    await it.response.send_message("「窓口を置いたよ！何かあればいつでも呼んでね！」", ephemeral=True)

# 管理系コマンドは以前と同じため略（必要に応じて含めてください）
@bot.tree.command(name="ban")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(it: discord.Interaction, member: discord.Member, reason: str = "特にないみたい"):
    await member.ban(reason=reason)
    await it.response.send_message(f"「えいっ！{member.display_name}を追い出したよ。理由は『{reason}』だね。これでみんな安心だよ！」")

keep_alive()
bot.run(os.getenv('DISCORD_TOKEN'))
