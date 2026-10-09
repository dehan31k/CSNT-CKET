import discord
from discord.ext import commands
import re
import time
from collections import defaultdict
from flask import Flask
from threading import Thread

# --- 7/24 AKTİF KALMA (WEB SERVER) ---
app = Flask('')

@app.route('/')
def home():
    return "Bot 7/24 Aktif!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# --- BOT AYARLARI ---
TOKEN = "BURAYA_BOT_TOKENINI_YAZ"
GELEN_GIDEN_KANAL_ID = 123456789012345678  # Gelen-giden mesaj kanalı ID
LOG_KANAL_ID = 123456789012345678          # Mute/Spam log kanalı ID

# Yasaklı kelime listesi (Küçük harfle yazın)
YASAKLI_KELIMELER = ["amk", "aq", "oç", "piç", "sik", "yarrak"]

# Spam tespiti için veri saklama: user_id -> [timestamp1, timestamp2, ...]
user_messages = defaultdict(list)
SPAM_LIMIT = 5       # Kaç mesajda spam sayılsın
SPAM_ZAMAN = 5       # Kaç saniye içinde

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# --- BOT HAZIR OLDUĞUNDA ---
@bot.event
async def on_ready():
    print(f'{bot.user.name} başarıyla giriş yaptı!')
    try:
        synced = await bot.tree.sync()
        print(f"Senkronize edilen komut sayısı: {len(synced)}")
    except Exception as e:
        print(f"Komutlar senkronize edilemedi: {e}")

# --- GELEN / GİDEN ÜYE KONTROLÜ ---
@bot.event
async def on_member_join(member):
    channel = bot.get_channel(GELEN_GIDEN_KANAL_ID)
    if channel:
        embed = discord.Embed(
            title="Hoş Geldin!",
            description=f"{member.mention} sunucumuza katıldı! Toplam üye sayısı: **{member.guild.member_count}**",
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
        await channel.send(embed=embed)

@bot.event
async def on_member_remove(member):
    channel = bot.get_channel(GELEN_GIDEN_KANAL_ID)
    if channel:
        embed = discord.Embed(
            title="Aramızdan Ayrıldı",
            description=f"{member.name} sunucudan ayrıldı. Kalan üye sayısı: **{member.guild.member_count}**",
            color=discord.Color.red()
        )
        await channel.send(embed=embed)

# --- KÜFÜR FİLTRESİ VE SPAM KORUMASI ---
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    content_lower = message.content.lower()
    log_channel = bot.get_channel(LOG_KANAL_ID)

    # 1. Küfür Kontrolü
    if any(re.search(rf"\b{re.escape(word)}\b", content_lower) for word in YASAKLI_KELIMELER):
        await message.delete()
        await message.channel.send(f"{message.author.mention}, lütfen üslubuna dikkat et!", delete_after=5)
        
        # Sorumlu kullanıcıya 5 dakika Mute (Timeout) at
        duration = discord.utils.utcnow() + discord.timedelta(minutes=5)
        await message.author.timeout(duration, reason="Küfürlü söylem kullanımı")
        
        if log_channel:
            await log_channel.send(f"⚠️ **Küfür Mute**: {message.author.mention} küfür ettiği için 5 dakika susturuldu.")
        return

    # 2. Spam Kontrolü
    now = time.time()
    user_id = message.author.id
    user_messages[user_id].append(now)

    # 5 saniyeden eski mesaj zaman damgalarını temizle
    user_messages[user_id] = [t for t in user_messages[user_id] if now - t < SPAM_ZAMAN]

    if len(user_messages[user_id]) >= SPAM_LIMIT:
        await message.channel.purge(limit=SPAM_LIMIT, check=lambda m: m.author == message.author)
        duration = discord.utils.utcnow() + discord.timedelta(minutes=10)
        await message.author.timeout(duration, reason="Spam yapılması")
        
        await message.channel.send(f"{message.author.mention}, spam yaptığın için 10 dakika susturuldun!", delete_after=5)
        if log_channel:
            await log_channel.send(f"🚫 **Spam Mute**: {message.author.mention} spam yaptığı için 10 dakika susturuldu.")
        user_messages[user_id].clear()
        return

    await bot.process_commands(message)

# --- TICKET (DESTEK) SİSTEMİ ---
class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 Ticket Aç", style=discord.ButtonStyle.primary, custom_id="create_ticket")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        user = interaction.user
        
        # Aynı kullanıcının açık bileti var mı kontrolü
        existing_channel = discord.utils.get(guild.channels, name=f"ticket-{user.name.lower()}")
        if existing_channel:
            await interaction.response.send_message(f"Zaten açık bir biletiniz var: {existing_channel.mention}", ephemeral=True)
            return

        # Kanal izinlerini ayarla (Kullanıcı ve Yönetici görebilir)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        channel = await guild.create_text_channel(name=f"ticket-{user.name}", overwrites=overwrites)
        
        embed = discord.Embed(
            title="Destek Talebi Oluşturuldu",
            description=f"Merhaba {user.mention}, yetkililer kısa süre içinde seninle ilgilenecektir.\n\nBileti kapatmak için aşağıdaki butona tıkla.",
            color=discord.Color.blue()
        )
        
        await channel.send(embed=embed, view=CloseTicketView())
        await interaction.response.send_message(f"Ticket kanalın oluşturuldu: {channel.mention}", ephemeral=True)

class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Ticket Kapat", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Bu ticket 5 saniye içinde siliniyor...")
        await discord.utils.sleep_until(discord.utils.utcnow() + discord.timedelta(seconds=5))
        await interaction.channel.delete()

@bot.tree.command(name="ticket-kur", description="Ticket oluşturma panelini kurar.")
@commands.has_permissions(administrator=True)
async def setup_ticket(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Destek Sistemi",
        description="Destek ekibimizle iletişime geçmek için aşağıdaki butona tıklayarak ticket açabilirsiniz.",
        color=discord.Color.green()
    )
    await interaction.channel.send(embed=embed, view=TicketView())
    await interaction.response.send_message("Ticket paneli başarıyla oluşturuldu!", ephemeral=True)

# 7/24 Çalıştırma Servisini Başlat
keep_alive()

# Botu Başlat
bot.run("MTU1ODE4Mzg5OTkzMzQ0MjA5OQ.G9VBfm.l6NqiSD1hqa9ASF_QQS86-9ONXVt30kS6RMzPo")
