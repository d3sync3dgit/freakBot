import discord
from discord import app_commands
from discord.ext import commands
import asyncio
from datetime import timedelta
from discord.ext import tasks
from datetime import datetime
import logging
import time

privilege_choices = [
    app_commands.Choice(name="Admin", value="Admin"),
    app_commands.Choice(name="Member", value="Member"),
    app_commands.Choice(name="Sub Citizen Coal Miner", value="Sub Citizen Coal Miner"),
    app_commands.Choice(name="Blacklist", value="Blacklist")
]

class MyBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not hasattr(self, 'tree'):
            self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()
        print("Command tree synced.")

    async def on_ready(self):
        print(f'We have logged in as {self.user}')

intents = discord.Intents.all()
intents.message_content = True  
intents.guilds = True
intents.members = True


bot = MyBot(command_prefix="/", intents=intents)

VALID_KEY = "V2S02R4"

risk_value = 9
privilege = "Member"
file_path = "database.txt"

def read_registered_users():
    with open(file_path, "r") as file:
        return [line.strip().split(",") for line in file.readlines()]

def write_registered_users(users):
    with open(file_path, "w") as file:
        for user in users:
            file.write(",".join(user) + "\n")

class Paginator(discord.ui.View):
    def __init__(self, interaction, users, page=0):
        super().__init__(timeout=60)
        self.interaction = interaction
        self.users = sorted(users, key=lambda x: (self.privilege_order(x[2]), -int(x[1])))
        self.page = page
        self.items_per_page = 7
        self.update_buttons()

    def privilege_order(self, privilege):
        order = {"Cat": 0, "Admin": 1, "Member": 2, "Sub Citizen Coal Miner": 3, "Blacklist": 4}
        return order.get(privilege, 5)

    def update_buttons(self):
        self.children[0].disabled = self.page <= 0
        self.children[1].disabled = self.page >= (len(self.users) - 1) // self.items_per_page

    #async def interaction_check(self, interaction: discord.Interaction) -> bool:
    #    return interaction.user == self.interaction.user

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.primary, custom_id="previous")
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 1
        await self.update_message(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary, custom_id="next")
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        await self.update_message(interaction)

    async def update_message(self, interaction: discord.Interaction):
        embed = await self.paginate_users()
        self.update_buttons()
        await interaction.response.edit_message(embed=embed, view=self)

    async def paginate_users(self):
        start = self.page * self.items_per_page
        end = start + self.items_per_page


        sorted_users = sorted(self.users, key=lambda user: int(user[1]))
        paginated_users = sorted_users[start:end]

        embed = discord.Embed(title="Registered Users", color=discord.Color.purple())
        for user in paginated_users:
            member = await self.interaction.guild.fetch_member(int(user[0]))
            embed.add_field(name=member.display_name, value=f"risk: {user[1]}, Privilege: {user[2]}", inline=False)
        
        embed.set_footer(text=f"Page {self.page + 1}/{(len(self.users) - 1) // self.items_per_page + 1}")
        return embed
    
    async def on_error(self, error: Exception, item: discord.ui.Item, interaction: discord.Interaction):
        # Log the error
        print(f"An error occurred: {error}")
        await interaction.response.send_message("An error occurred while processing your request. Please try again later.", ephemeral=True)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        await self.interaction.edit_original_response(view=self)
    

class UserGroup(commands.GroupCog, name="user"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        super().__init__()

    async def check_privileges(self, interaction: discord.Interaction):
        users = read_registered_users()
        user_info = next((user for user in users if user[0] == str(interaction.user.id)), None)
        if not user_info or user_info[2] != "Admin":
            await interaction.response.send_message("You do not have the right privileges to execute this command.", ephemeral=True)
            return False
        return True

    @app_commands.command(name="register", description="Register a new user")
    async def register(self, interaction: discord.Interaction, key: str):
        if key != VALID_KEY:
            await interaction.response.send_message("Invalid registration key.", ephemeral=True)
            return

        member = interaction.user
        users = read_registered_users()
        if any(user[0] == str(member.id) for user in users):
            await interaction.response.send_message("User is already registered.", ephemeral=True)
            return

        users.append([str(member.id), str(risk_value), privilege])
        write_registered_users(users)
        role = discord.utils.get(interaction.guild.roles, name="db connected")
        await member.add_roles(role)
        embed = discord.Embed(title="User Created", description=f"User: {member.mention}\nrisk: {risk_value}\nPrivilege: {privilege}", color=discord.Color.purple())
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="add", description="Add a new user with default member role and risk level 1")
    async def create_user(self, interaction: discord.Interaction, member: discord.Member):
        if not await self.check_privileges(interaction):
            return

        users = read_registered_users()
        if any(user[0] == str(member.id) for user in users):
            await interaction.response.send_message("User is already registered.", ephemeral=True)
            return

        users.append([str(member.id), str(risk_value), privilege])
        write_registered_users(users)
        role = discord.utils.get(interaction.guild.roles, name="db connected")
        await member.add_roles(role)
        embed = discord.Embed(title="User added", description=f"User: {member.mention}\nrisk: {risk_value}\nPrivilege: {privilege}", color=discord.Color.purple())
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="edit", description="Edit an existing user")
    @app_commands.describe(member="The member to edit", privilege="The new privilege", risk="The new risk level")
    @app_commands.choices(privilege=privilege_choices)
    async def edit(self, interaction: discord.Interaction, member: discord.Member, privilege: app_commands.Choice[str], risk: int):
        if not await self.check_privileges(interaction):
            return
        if not member or not privilege or not risk:
            await interaction.response.send_message("You must provide a member, privilege, and risk level to edit.", ephemeral=True)
            return
        if risk > 10:
            await interaction.response.send_message("risk level cannot be greater than 10.", ephemeral=True)
            return
        users = read_registered_users()
        for user in users:
            if user[0] == str(member.id):
                if privilege:
                    user[2] = privilege.value
                if risk:
                    user[1] = str(risk)
                break
        write_registered_users(users)
        embed = discord.Embed(title="User Edited", description=f"User: {member.mention}\nrisk: {user[1]}\nPrivilege: {user[2]}", color=discord.Color.purple())
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="remove", description="Remove an existing user")
    async def remove(self, interaction: discord.Interaction, member: discord.Member):
        if not await self.check_privileges(interaction):
            return
        if not member:
            await interaction.response.send_message("You must mention a member to remove.", ephemeral=True)
            return
        users = read_registered_users()
        users = [user for user in users if user[0] != str(member.id)]
        write_registered_users(users)
        role = discord.utils.get(interaction.guild.roles, name="db connected")
        await member.remove_roles(role)
        embed = discord.Embed(title="User Removed", description=f"User: {member.mention} has been removed.", color=discord.Color.purple())
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="list", description="List all registered users")
    async def list_users(self, interaction: discord.Interaction):
        users = read_registered_users()
        paginator = Paginator(interaction, users)
        embed = await paginator.paginate_users()
        await interaction.response.send_message(embed=embed, view=paginator)
        

    @app_commands.command(name="info", description="Get user info")
    async def user_info(self, interaction: discord.Interaction, member: discord.Member):
        users = read_registered_users()
        user_info = next((user for user in users if user[0] == str(member.id)), None)
        if not user_info:
            await interaction.response.send_message("User not found.", ephemeral=True)
            return
        embed = discord.Embed(title="User Info", description=f"User: {member.mention}\nrisk: {user_info[1]}\nPrivilege: {user_info[2]}", color=discord.Color.purple())
        await interaction.response.send_message(embed=embed)

class ModGroup(commands.GroupCog, name="mod"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def check_privileges(self, interaction: discord.Interaction):
        users = read_registered_users()
        user_info = next((user for user in users if user[0] == str(interaction.user.id)), None)
        if not user_info or user_info[2] != "Admin":
            await interaction.response.send_message("You do not have the right privileges to execute this command.", ephemeral=True)
            return False
        return True

    @app_commands.command(name="kick", description="Kick a user from the server")
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        if not await self.check_privileges(interaction):
            return
        users = read_registered_users()
        for user in users:
            if user[0] == str(member.id) and user[2].lower() == "admin":
                await interaction.response.send_message("You cannot kick a member with Admin privileges.", ephemeral=True)
                return
        await member.kick(reason=reason)
        embed = discord.Embed(title="User Kicked", description=f"User: {member.mention}\nReason: {reason}", color=discord.Color.red())
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="ban", description="Ban a user from the server")
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        if not await self.check_privileges(interaction):
            return
        users = read_registered_users()
        for user in users:
            if user[0] == str(member.id) and user[2].lower() == "admin":
                await interaction.response.send_message("You cannot ban a member with Admin privileges.", ephemeral=True)
                return
        await member.ban(reason=reason)

        users = read_registered_users()

        

        user_exists = any(user[0] == str(member.id) for user in users)

        if user_exists:
            users = [user for user in users if user[0] != str(member.id)]
            write_registered_users(users)

            embed = discord.Embed(title="User Banned",description=f"User: {member.mention}\nReason: {reason}\n\nUser has been removed from the database.",color=discord.Color.red())
        else:
            embed = discord.Embed(title="User Banned",description=f"User: {member.mention}\nReason: {reason}\n\nUser was not found in the database.",color=discord.Color.red())
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="timeout", description="Timeout a user in the server")
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, days: int = 0, hours: int = 0, minutes: int = 0, seconds: int = 0, reason: str = "No reason provided"):
        if not await self.check_privileges(interaction):
            return
        duration = timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
        try:
            await member.timeout(duration, reason=reason)
            embed = discord.Embed(title="User Timed Out", description=f"User: {member.mention}\nDuration: {duration}\nReason: {reason}", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            await interaction.response.send_message(f"Failed to timeout user: {e}", ephemeral=True)

    @app_commands.command(name="untimeout", description="Remove timeout from a user in the server")
    async def untimeout(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        if not await self.check_privileges(interaction):
            return
        try:
            await member.timeout(None, reason=reason)
            embed = discord.Embed(title="User Timeout Removed", description=f"User: {member.mention}\nReason: {reason}", color=discord.Color.green())
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            await interaction.response.send_message(f"Failed to remove timeout from user: {e}", ephemeral=True)        

    @app_commands.command(name="unban", description="Unban a user by Discord ID")
    async def unban(self, interaction: discord.Interaction, user_id: str):
        if not await self.check_privileges(interaction):
            return
        try:
            user = await self.bot.fetch_user(int(user_id))
            await interaction.guild.unban(user)
            embed = discord.Embed(
                title="User Unbanned",
                description=f"User: {user.mention} has been successfully unbanned.",
                color=discord.Color.green()
            )
        except discord.NotFound:
            print(f"User with ID {user_id} not found")
            embed = discord.Embed(
                title="Unban Failed",
                description=f"User with ID: {user_id} was not found.",
                color=discord.Color.red()
            )
        except discord.Forbidden:
            print("Bot does not have permission to unban users")
            await interaction.response.send_message("I do not have permission to unban users.", ephemeral=True)
            return
        except discord.HTTPException as e:
            print(f"Failed to unban user: {e}")
            await interaction.response.send_message("Failed to unban user due to an error.", ephemeral=True)
            return

        await interaction.response.send_message(embed=embed)

class RegHelp(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="register_help", description="Show how to use the register command")
    async def register_help(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="How to Use the Register Command",
            description="To register a new user, use the following command:",
            color=discord.Color.purple()
        )
        embed.add_field(
            name="Command",
            value="/user register key:********",
            inline=True
        )
        embed.set_footer(text="P.S you shouldn't be here if you don't know the key ;)")
        await interaction.response.send_message(embed=embed)

class ListTracker(commands.GroupCog, name="listtracker"):
    def __init__(self, bot):
        self.bot = bot
        self.list_users_loop.start()

    def read_looping_state(self):
        try:
            with open('DatabaseConstant.txt', 'r') as file:
                state = file.read().strip()
                return state == 'True'
        except FileNotFoundError:
            return False

    async def check_privileges(self, interaction: discord.Interaction):
        users = read_registered_users()
        user_info = next((user for user in users if user[0] == str(interaction.user.id)), None)
        if not user_info or user_info[2] != "Admin":
            await interaction.response.send_message("You do not have the right privileges to execute this command.", ephemeral=True)
            return False
        return True

    @app_commands.command(name="on")
    async def on(self, interaction: discord.Interaction):
        await interaction.response.defer() 
        if not await self.check_privileges(interaction):
            return
        if not self.read_looping_state():
            self.current_channel = interaction.channel 
            await self.send_user_list(interaction)
            embed = discord.Embed(
                title="List Tracking Enabled",
                description="List tracking has been enabled.",
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=embed)  
            with open('DatabaseConstant.txt', 'w') as file:
                file.write('True')
        else:
            await interaction.followup.send("List tracking is already enabled.", ephemeral=True)

    @app_commands.command(name="off")
    async def off(self, interaction: discord.Interaction):
        await interaction.response.defer() 
        if not await self.check_privileges(interaction):
            return
        if self.read_looping_state():
            embed = discord.Embed(
                title="List Tracking Disabled",
                description="List tracking has been disabled.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)  
            with open('DatabaseConstant.txt', 'w') as file:
                file.write('False')
        else:
            await interaction.followup.send("List tracking is already disabled.", ephemeral=True)

    @tasks.loop(hours=1)
    async def list_users_loop(self):
        if self.read_looping_state() and self.current_channel:
            await self.send_user_list(self.current_channel)

    async def send_user_list(self, interaction: discord.Interaction):
        print("Sending user list")
        embed = self.get_user_list_embed(interaction)
        print("test")
        await interaction.followup.send(embed=embed) 

    def get_user_list_embed(self, interaction: discord.Interaction):
        users = []
        try:
            with open('database.txt', 'r') as file:
                for line in file:
                    try:
                        user_id, risk, privilege = line.strip().split(',')
                        users.append({'id': int(user_id), 'risk': int(risk), 'privilege': privilege})
                    except ValueError as e:
                        logging.error(f"Error parsing line: {line.strip()} - {e}")
        except FileNotFoundError as e:
            logging.error(f"File not found: {e}")
        except Exception as e:
            logging.error(f"An unexpected error occurred: {e}")

        users.sort(key=lambda x: x['risk'])

        embed = discord.Embed(
            title="User List",
            description="List of all users with their risk and privilege, sorted by risk (low to high)",
            color=discord.Color.purple(),
            timestamp=datetime.utcnow() 
        )

        for user in users:
            member = interaction.guild.get_member(user['id'])
            if member:
                embed.add_field(
                    name=member.display_name,  
                    value=f"Risk: {user['risk']}, Privilege: {user['privilege']}",
                    inline=False
                )

        return embed
    
class NikBas(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="REMOVED FOR PRIVACY")
    async def nikolos_bashivilli(self, interaction: discord.Interaction):
        await interaction.response.send_message("REMOVED FOR PRIVACY", ephemeral=False)

class Info(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
    @app_commands.command(name="info")
    async def infocom(self, interaction: discord.Interaction):
        start_time = time.time()
        embed = discord.Embed(
            title="Freak Bot V2.1",
            description="Developed and maintained by <@1056050756324696194>",
            color=discord.Color.purple()
        )
        end_time = time.time()
        response_time_ms = (end_time - start_time) * 1000
        embed.set_footer += f"FreakBot c. 2024 by VSR, Response time: {response_time_ms:.2f} ms"
        await interaction.response.send_message(embed=embed)

### make it auto send when a change has been made to database instead of every hour

async def main():
    await bot.add_cog(UserGroup(bot))
    await bot.add_cog(ModGroup(bot))
    await bot.add_cog(RegHelp(bot))
    await bot.add_cog(ListTracker(bot))
    await bot.add_cog(NikBas(bot))
    await bot.start("TOKEN")

asyncio.run(main())


