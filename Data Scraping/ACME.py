#===================================================================
# Imports
#===================================================================

# Selenium Imports
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException

# Data Handling Imports
import numpy as np
import pandas as pd

# Datetime Imports
import datetime
from datetime import date, timedelta

# Utility Imports
from tqdm import tqdm
import os

#===================================================================
# Settings
#===================================================================
    
url = "https://acme.wisc.edu/tools/schedule/schedule.php"
staff_url = "https://acme.wisc.edu/tools/staff/index.php"
login_secret = os.path.join("src", "secrets", "login.secret")

schedule_block_length = 0.5 # in hours

#===================================================================
# Constants
#===================================================================

days_in_months = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
default_pay = 10.25
pay_rates = {
    "Support Specialist" : 10.25, # Pick 1
    "SLP Web Writer" : 12.75, # Student Technical Writer
    "SLP Developer" : 12.75, # Student Developer
    "SLP WiscIT Lead" : 13.75, # Student WiscIT Lead
    "SLP Data Metrics Lead" : 12.75, # Student Data & Metrics Lead
    "SLP Team Lead" : 13.75 # Student Team Lead
}
pay_raises = {
    "Pick 3" : 0.50, # Advanced Phone Agent
    "Chat/Email" : 0.50,
    "HDQA" : 0.75
}
non_agents = ["", "PETE", "HDP1", "HDP2", "HDP3", "HDP4"]
fte_agents = ["YANG", "MIMO", "HPRI", "SSCH"]
role_groups = {
    "ALL" : [
        "HDQA", "Floor Supervisor", "Tech Store", "Phones", "Chat/Email", "Email", "HDQA (Remote)",
        "Supervisor (Remote)", "Phones (FTE)", "Phones (Remote)", "Trainer/Phones", "Chat/Email (Remote)",
        "Chat (Remote)", "Email (Remote)", "HDL1 Project", "Walk-in [Lead]", "Walk-in Counter", "Walk-in SD",
        "Repair", "WiHD onsite FTE", "WiHD Appt", "STL Outreach", "Training", "Event", "Meeting"
    ],
    "ALL_STUDENTS" : [
        "HDQA", "Tech Store", "Phones", "Chat/Email", "Email", "HDQA (Remote)", "Phones (Remote)",
        "Trainer/Phones", "Chat/Email (Remote)", "Chat (Remote)", "Email (Remote)", "HDL1 Project", 
        "Walk-in [Lead]", "Walk-in Counter", "Walk-in SD", "Repair", "WiHD Appt", "STL Outreach", "Training"
    ],
    "ALL_HDQA" : ["HDQA", "HDQA (Remote)"],
    "STL" : ["HDL1 Project", "STL Outreach"],
    "WALK_IN" : ["Tech Store", "Walk-in [Lead]", "Walk-in Counter", "Walk-in SD", "Repair", "WiHD onsite FTE", "WiHD Appt"],
    "ALL_PHONES" : ["Phones", "Phones (FTE)", "Phones (Remote)", "Trainer/Phones"],
    "ALL_CHAT_EMAIL" : ["Chat/Email", "Email", "Chat/Email (Remote)", "Chat (Remote)", "Email (Remote)"],
    "ALL_TRAINING" : ["Trainer/Phones", "Chat/Email (Remote)", "Training"],
    "MEETING_AND_EVENT" : ["Event", "Meeting"]
}

#===================================================================
# ACME Class
#===================================================================

class ACME:
    
    #===================================================================
    # Setup
    #===================================================================
    
    def __init__(self, headless = False):
        # Set Mode
        self.options = Options()
        self.options.headless = headless
        
        # Get Secrets
        with open(login_secret) as f:
            self.user = f.readline()[:-1]
            self.password = f.readline()
            
        # Setup Cache
        self.schedule_cache = {}
        self.agent_pay_cache = {}
    
    # Login to ACME
    def Login(self):
        browser = webdriver.Chrome(options=self.options)
        browser.get(url)

        # Fill in username
        user_field = browser.find_element_by_id('j_username')
        user_field.send_keys(self.user)

        # Fill in password
        pass_field = browser.find_element_by_id('j_password')
        pass_field.send_keys(self.password)

        # Click login
        login_button = browser.find_element_by_name('_eventId_proceed')
        login_button.click()

        # Return ACME pointed browser
        self.browser = browser
        return self.browser
    
    #===================================================================
    # ACME Functionality
    #===================================================================
    
    # Get Schedule Table by Date (as string)
    def GetScheduleByDate(self, day=None):
        # Default to today
        if day == None:
            day = self.DateToString(date.today())
        
        # Check if table is in cache
        if day in self.schedule_cache:
            return { day: self.schedule_cache[day] }
        
        # Access page for specified date
        new_url = url + '?date=' + day
        browser = self.browser
        browser.get(new_url)

        # Get table headers
        header_html = browser.find_element_by_xpath("//thead[1]/tr").get_attribute('innerHTML')
        headers = []
        header_text = header_html.split(" ")
        for line in header_text:
            if line.startswith('id='):
                parts = line.split('"')
                header = parts[1]
                parts = header.split('_')
                headers.append(parts[1])
        headers.append("total")

        # Get table
        table = browser.find_element_by_id('sch_table_verticle')
        table_html = table.get_attribute('outerHTML')
        df = pd.read_html(table_html)[0]
        df.drop(df.tail(2).index,inplace=True)

        # Set headers of dataframe
        columns = df.columns
        new_names = {}
        for i in range(len(columns)):
            new_names[columns[i]] = headers[i]
        df = df.rename(columns=new_names)
        df = df.set_index('time')
        df = df.drop(columns=['total'])

        # Split up agents
        for col in df:
            data = df[col]
            new_data = []
            for row in data:
                if type(row) != str:
                    new_data.append(None)
                else:
                    agents = [row[i:i+4] for i in range(0, len(row), 4)]
                    new_data.append(agents)
            df[col] = new_data
        
        # Cache and return schedule table
        self.schedule_cache[day] = df
        return { day: df }
    
    # Get Schedule Tables by Month (and year) - MM, YYYY - defaults to this month
    def GetSchedulesByMonth(self, month=None, year=None):
        # Set starting point, defaulting to this month
        if month == None:
            month = date.today().month;
        if year == None:
            year = date.today().year
        num_days = self.DaysInMonth(month, year)
        start = self.StringToDate(str(year) + '-' + str(month) + '-' + str(1))

        # Get all dates in the month
        dates = []
        for i in range(num_days):
            day = start + timedelta(days=i)
            dates.append(day)

        # Get tables for the month
        tables = {}
        for day in tqdm(dates, desc="Scraping data for month: " + str(month) + ", " + str(year)):
            day_str = self.DateToString(day)
            table = self.GetScheduleByDate(day_str)[day_str]
            tables[day_str] = table

        # Return all the tables in order from start of month
        return tables
    
    # Get tables from all dates in range, returns no data if invalid range, end defaults to today
    def GetSchedulesInRange(self, start_date, end_date=None):
        # Get start date
        start = self.StringToDate(start_date)
        
        # Set end of range as today if not given
        if end_date == None:
            end = date.today()
        else:
            end = self.StringToDate(end_date)

        # Get all dates in provided range
        num_days = (end - start).days + 1;
        if (num_days < 0):
            return {}

        # Get all dates in the range
        dates = []
        for i in range(num_days):
            day = start + timedelta(days=i)
            dates.append(day)

        # Get tables for all dates in range
        tables = {}
        for day in tqdm(dates, desc="Scraping data for date range"):
            day_str = self.DateToString(day)
            table = self.GetScheduleByDate(day_str)[day_str]
            tables[day_str] = table

        # Return all the tables in order from start to end
        return tables
    
    # Get tables from n days (defaults to a week)
    def GetRecentSchedules(self, num_days=7):
        # Get last n days
        today = date.today()
        dates = []
        for i in range(num_days):
            day = today - timedelta(days=i)
            dates.append(day)

        # Get tables for last n days
        tables = {}
        for day in tqdm(dates, desc="Scraping data by day"):
            day_str = self.DateToString(day)
            table = self.GetScheduleByDate(day_str)[day_str]
            tables[day_str] = table

        # Return all the tables
        return tables
    
    # Get filtered tables only including certain roles
    def GetSchedulesByRole(self, tables, role):
        # Setup list of included roles to keep
        roles = []
        
        # Check if role is a role group, and add all included roles
        if role in role_groups:
            for matching_role in role_groups[role]:
                roles.append(self.SimplifyString(matching_role))
        # Otherwise assume role is a specific role and only add it
        else:
            roles.append(self.SimplifyString(role))
            
        # Go through tables and trim down to only selected roles
        for date in tables.keys():
            # Refresh the table to retrieve all roles lost in previous filters
            tables[date] = self.GetScheduleByDate(date)[date]
            for col in tables[date]:
                # Remove columns not matching requested roles
                if col not in roles:
                    tables[date] = tables[date].drop(columns=[col])
        
        # Return the filtered tables
        return tables
    
    # Get hours worked by agent in set of tables
    def GetAgentHours(self, tables, most_first=True):
        # Keep track of all agents as they pop up
        agent_hours = {}
        
        # Iterate through all provided data
        for date in tables.keys():
            for col in tables[date]:
                for entry in tables[date][col]:
                    if entry != None:
                        for agent in entry:
                            # Create entry for agent upon first listing
                            if agent not in agent_hours:
                                agent_hours[agent] = 0
                            # Increment by half hour for each entry
                            agent_hours[agent] += schedule_block_length
        
        # Return list sorted by most to least hours
        agent_hours = {k: v for k, v in sorted(agent_hours.items(), key=lambda item: item[1], reverse=most_first)}
        return agent_hours
    
    # Get estimated pay rate for agent based on listed position and trainings
    def GetAgentPay(self, agent_code):
        # Base Cases, Posted Shifts, FTE Agents
        if agent_code in non_agents or agent_code in fte_agents:
            return 0
        
        # Check if agent pay is in cache
        if agent_code in self.agent_pay_cache:
            return self.agent_pay_cache[agent_code]
        
        # Direct browser to staff utility
        browser = self.browser
        browser.get(staff_url)
        
        try:
            # Fill in 4 letter
            agent_field = browser.find_element_by_name("login")
            agent_field.send_keys(agent_code)
            # Check include inactive box
            inactive_field = browser.find_element_by_name("inactive")
            inactive_field.click()
            # Submit button
            submit_field = browser.find_element_by_css_selector("[value='Search']")
            submit_field.click()

            # Get Job Titles
            job_field = browser.find_element_by_xpath("//*[contains(text(),'Position')]/following-sibling::*")
            base_job = job_field.text
            # Get Trainings
            trainings_field = job_field.find_element_by_xpath("./../following-sibling::*/*[2]")
            items = trainings_field.find_elements_by_tag_name("li")
            trainings = []
            for item in items:
                trainings.append(item.text)

            # Calculate pay
            if base_job in pay_rates:
                pay = pay_rates[base_job]
            else:
                pay = default_pay
            if not "SLP" in base_job:
                for pay_raise in pay_raises:
                    if pay_raise in trainings:
                        pay += pay_raises[pay_raise]
        except:
            pay = default_pay
        
        # Cache and return the pay for this agent
        self.agent_pay_cache[agent_code] = pay
        return pay
    
    # Get the total cost of paying agents based on set of agent hours
    def GetScheduleCost(self, tables, day_avg=False, total=False):
        # Get hours worked by each agent in this data
        agent_hours = self.GetAgentHours(tables)
        
        # Get pay for each agent
        pay_rates = {}
        agent_pay = {}
        for agent in tqdm(agent_hours, desc="Scraping Data by Agent"):
            pay_rates[agent] = self.GetAgentPay(agent)
            # if (pay_rates[agent] == 0):
            #     agent_pay.pop(agent, None)
            # else:
            agent_pay[agent] = pay_rates[agent] * agent_hours[agent]
        
        # Divide pay over time period if requested
        if day_avg:
            for agent in agent_pay:
                agent_pay[agent] /= len(tables)
                
        # Return either by agent or a total cost
        if (total):
            return sum(agent_pay.values())
        else:
            return agent_pay
             
    # Close the browser
    def Close(self):
        self.browser.close()
    
    #===================================================================
    # Utilities
    #===================================================================

    # URL String to Date: String form = date=YYYY-MM-DD
    def StringToDate(self, string):
        parts = string.split('-')
        year = int(parts[0])
        month = int(parts[1])
        day = int(parts[2])
        date = datetime.date(year=year, month=month, day=day)
        return date

    # Date to URL String: String form = date=YYYY-MM-DD
    def DateToString(self, date):
        year = date.year
        month = date.month
        day = date.day
        return str(year) + '-' + str(month) + '-' + str(day)
    
    # Get days in month (MM, YYYY)
    def DaysInMonth(self, month, year=None):
        month = int(month) - 1
        if (year == None):
            year = int(date.today().year)
        else:
            year = int(year)
        
        # February Leap Year
        if (month == 1 and year % 4 == 0):
            return days_in_months[month] + 1
        else:
            return days_in_months[month]
        
    # Parse a string to be all lowercase, no symbols, no spaces
    def SimplifyString(self, string):
        # To lowercase
        simple_string = string.lower()
        # Replace spaces
        simple_string = simple_string.replace(" ", "")
        # Replace symbols
        simple_string = simple_string.replace("-", "").replace("/", "").replace("\\", "")
        # Replace brackets
        simple_string = simple_string.replace("[", "").replace("]", "").replace("(", "").replace(")", "")
        
        return simple_string
    
    #===================================================================
    # Schedule Builder Scraping
    #===================================================================
    
    # Get a list of trainings each agent has
    def GetAgentTrainings(self, agent_code):
        # Base Cases, Posted Shifts, FTE Agents
        if agent_code in non_agents or agent_code in fte_agents:
            return []
        
        # Direct browser to staff utility
        browser = self.browser
        browser.get(staff_url)
        
        try:
            # Fill in 4 letter
            agent_field = browser.find_element_by_name("login")
            agent_field.send_keys(agent_code)
            # Check include inactive box
            inactive_field = browser.find_element_by_name("inactive")
            inactive_field.click()
            # Submit button
            submit_field = browser.find_element_by_css_selector("[value='Search']")
            submit_field.click()

            # Get Job Titles
            job_field = browser.find_element_by_xpath("//*[contains(text(),'Position')]/following-sibling::*")
            base_job = job_field.text
            # Get Trainings
            trainings_field = job_field.find_element_by_xpath("./../following-sibling::*/*[2]")
            items = trainings_field.find_elements_by_tag_name("li")
            trainings = []
            for item in items:
                trainings.append(item.text)
        except:
            base_job = None
            trainings = []

        # Summarize agent job info as base job and trainings
        job_info = {}
        job_info["Base"] = base_job
        job_info["Trainings"] = []
        for training in trainings:
            job_info["Trainings"].append(training)
            
        return job_info
    
    # Get the total trainings of each agent
    def GetScheduledAgentTrainings(self, tables):        
        # Get hours worked by each agent in this data
        agent_hours = self.GetAgentHours(tables)
        
        # Get trainings for each agent
        agent_trainings = {}
        agent_pay = {}
        for agent in tqdm(agent_hours, desc="Scraping Data by Agent"):
            agent_trainings[agent] = self.GetAgentTrainings(agent)
        
        # Return the 
        return agent_trainings