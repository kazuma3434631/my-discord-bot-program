import discord
from discord.ext import commands
from discord import app_commands
import os
from keep_alive import keep_alive

# 1. 権限（Intents）の設定
intents = discord.Intents.default()
intents.members = True 
intents.message_content = True

bot = commands.Bot(command_prefix='/', intents=intents)

# --- 設定 ---
LOG_CHANNEL_ID = 1475491103225417738
WELCOME_CHANNEL_ID = 1475484575114330162

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f'ログイン完了: {bot.user.name}')
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        await channel.send("botが起動しました")

# --- /say コマンド ---
@bot.tree.command(name="say", description="【管理者専用】Botに好きな言葉を喋らせます")
@app_commands.describe(message="Botに喋らせたい内容を入力してください")
@app_commands.checks.has_permissions(administrator=True)
async def say(interaction: discord.Interaction, message: str):
    # チャンネルに送信
    sent_message = await interaction.channel.send(message)
    
    # 送信したメッセージのIDを本人にだけ教えてあげる（後で修正する時に使うため）
    await interaction.response.send_message(
        f"メッセージを送信しました！\n修正用ID: `{sent_message.id}`", 
        ephemeral=True
    )

# --- /edit コマンド (後から内容を変更する) ---
@bot.tree.command(name="edit", description="【管理者専用】Botが送ったメッセージを書き換えます")
@app_commands.describe(
    message_id="修正したいメッセージのIDを入力してください",
    new_text="新しい内容を入力してください"
)
@app_commands.checks.has_permissions(administrator=True)
async def edit(interaction: discord.Interaction, message_id: str, new_text: str):
    try:
        # IDからメッセージを探す
        target_msg = await interaction.channel.fetch_message(int(message_id))
        
        # Bot自身のメッセージか確認して編集
        if target_msg.author == bot.user:
            await target_msg.edit(content=new_text)
            await interaction.response.send_message("✅ メッセージを修正したよ！", ephemeral=True)
        else:
            await interaction.response.send_message("❌ それは私のメッセージじゃないみたい…", ephemeral=True)
            
    except Exception as e:
        await interaction.response.send_message(f"❌ 修正できなかったよ…（IDが間違っているかも？）\nエラー: {e}", ephemeral=True)

# --- 参加・退出メッセージ (シンプル版に戻しました) ---
@bot.event
async def on_member_join(member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if channel:
        await channel.send(f"{member.display_name}さん、こんにちは！「{member.guild.name}」へようこそ")

@bot.event
async def on_member_remove(member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if channel:
        await channel.send(f"{member.display_name}さん、さようなら…バイ…バイ…")

# --- /ping コマンド ---
@bot.tree.command(name="ping", description="Botの応答速度を確認します")
async def ping(interaction: discord.Interaction):
    ping_ms = round(bot.latency * 1000)
    await interaction.response.send_message(f"Pong! 🏓\n応答速度: {ping_ms}ms")

# 2. 起動
keep_alive()
TOKEN = os.getenv('DISCORD_TOKEN') or 'YOUR_BOT_TOKEN_HERE'
bot.run(TOKEN)
