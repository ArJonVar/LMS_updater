import smartsheet
from smartsheet.exceptions import ApiError
from smartsheet_grid import grid
from datetime import datetime, timedelta
import requests
from requests.structures import CaseInsensitiveDict 
import json
import time
from globals import smartsheet_token, bamb_token, learnupon_token, bamb_token_base64, dev_bamb_token, dev_bamb_token_base64, learnupon_basicauth
from logger import ghetto_logger

class LmsUpdater():
    '''Explain Class'''
    def __init__(self, config):
        self.dev=config.get('dev')
        self.config = config
        self.smartsheet_token=config.get('smartsheet_token')
        self.bamb_token=config.get('bamb_token')
        self.learnupon_token=config.get('learnupon_token')
        self.learnupon_basicauth=config.get('learnupon_basicauth')
        self.bamb_token_base64=config.get('bamb_token_base64')
        grid.token=smartsheet_token
        self.smart = smartsheet.Smartsheet(access_token=self.smartsheet_token)
        self.smart.errors_as_exceptions(True)
        self.start_time = time.time()
        self.log=ghetto_logger("lms_updater.py", self.smart, grid)
        self.log.log('Script STARTED')

#region base api calls
    def pull_hris_users(self):
        '''bambooHR report 512 has all the parameters designed for this system'''

        url = "https://api.bamboohr.com/api/gateway.php/dowbuilt/v1/reports/512?format=JSON&onlyCurrent=true"
        dev_url = "https://api.bamboohr.com/api/gateway.php/dowbuilttest/v1/reports/101?format=JSON&onlyCurrent=true"
        headers = {"authorization": f"Basic {self.bamb_token_base64}"}
        if self.dev == True:
            resp = requests.get(dev_url, headers=headers)
        else:
            resp = requests.get(url, headers=headers)
        
        self.hris_usr_list=json.loads(resp.text).get('employees')  
        if resp.status_code in [200, 201, 202]:
            self.log.log('hris data pulled')  
    def setup_inputs(self, employee):
        '''this code was taken off of Zapier that had a specific system of inputs that I am mirroring here to minimize code changes'''
        e = employee
        inputs = {
            'hris_first': e.get('firstName'), 
            'hris_last':e.get('lastName'),
            "hris_uuid": e.get('employeeNumber'), 
            'hris_status': e.get('status'),
            'sup': e.get('-44'), 
            'work_email': e.get('workEmail'),
            'hris_department': e.get('department'),
            'hris_jobTitle':e.get('jobTitle'),
            'hris_hireDate':e.get('hireDate'),
            'auth_token': self.learnupon_token
        }
        self.single_user_data['input_dict'] = inputs
    def pull_ss_exemptions(self):
        '''list of employees that should not be updated if the exemption is active'''
        sheet = grid(6059768607100804)
        sheet.fetch_content()
        sheet.df
        self.active_exceptions = sheet.df[sheet.df['Exception Active'] == True]['Employee Email'].to_list()
    def pull_lms_users(self):
        '''pulls user data that can help grab user id, and check if changes need to be made to user'''
        url = "https://dowbuilt.learnupon.com/api/v1/users"
        headers = CaseInsensitiveDict()
        headers["Content-Type"] = "application/json"
        headers["Authorization"] = f"Basic {self.learnupon_token}" # Your authorization token here
        resp = requests.get(url, headers=headers)
        resp_data = json.loads(resp.content.decode('utf-8'))
        self.lms_usr_list=resp_data
        if resp.status_code in [200, 201, 202]:
            self.log.log('lms data pulled')
    def update_lms_user(self):
        '''Update a user in the LMS.'''
        url = f"https://dowbuilt.learnupon.com/api/v1/users/{self.single_user_data['processed_dict'].get('lms_id')}"
        headers = CaseInsensitiveDict()
        headers["Content-Type"] = "application/json"
        headers["Authorization"] = f"Basic {self.learnupon_token}" # Your authorization token here
        data = {
            "User": {
                "first_name": self.single_user_data['input_dict'].get('hris_first'),
                "last_name": self.single_user_data['input_dict'].get('hris_last'),
                "email": self.single_user_data['processed_dict'].get('work_email'),
                "enabled": self.single_user_data['processed_dict'].get('enabled'),
                "username": self.single_user_data['input_dict'].get('six_dig_hris_uuid'),
                "CustomData": {
                    "isSupervisor": self.single_user_data['processed_dict'].get('isSupervisor'),
                    "hireDate": self.single_user_data['hris_dict'].get('hireDate'),
                    "location": self.single_user_data['hris_dict'].get('location'),
                    "division": self.single_user_data['hris_dict'].get('division'),
                    "jobTitle": self.single_user_data['hris_dict'].get('jobTitle'),
                    "reportingTo": self.single_user_data['hris_dict'].get('91'),
                    "department": self.single_user_data['hris_dict'].get('department')
                }
            }
        }
        resp = requests.put(url, headers=headers, json=data)
        if resp.status_code in [200, 201, 202]:
            self.log.log(f'{self.single_user_data["processed_dict"]["user"]} updated in lms')
        api_data=json.loads(resp.content.decode('utf-8'))
        self.single_user_data['processed_dict']['update_usr_request'] = api_data
        # print(api_data)
        print(f"updated user: {self.single_user_data['processed_dict'].get('user')}")
    def new_lms_user(self):
        '''adds new user to LMS, gets LMS id back, adds it to the group_membership_dict, so usr can be added to group'''
        url = f"https://dowbuilt.learnupon.com/api/v1/users"
        headers = CaseInsensitiveDict()
        headers["Content-Type"] = "application/json"
        headers["Authorization"] = f"Basic {self.learnupon_token}" # Your authorization token here
        data = {
            "User": {
                "first_name": self.single_user_data['input_dict'].get('hris_first'),
                "last_name": self.single_user_data['input_dict'].get('hris_last'),
                "email": self.single_user_data['processed_dict'].get('work_email'),
                "password": 'Dowbuilt!',
                "enabled": True,
                "user_type": 'learner',
                "username": self.single_user_data['input_dict'].get('six_dig_hris_uuid'),
                "CustomData": {
                    "isSupervisor": self.single_user_data['processed_dict'].get('isSupervisor'),
                    "hireDate": self.single_user_data['hris_dict'].get('hireDate'),
                    "location": self.single_user_data['hris_dict'].get('location'),
                    "division": self.single_user_data['hris_dict'].get('division'),
                    "jobTitle": self.single_user_data['hris_dict'].get('jobTitle'),
                    "reportingTo": self.single_user_data['hris_dict'].get('91'),
                    "department": self.single_user_data['hris_dict'].get('department')
                }
            }
        }
        print(data)
        resp = requests.post(url, headers=headers, json=data)
        if resp.status_code in [200, 201, 202]:
            self.log.log(f'{self.single_user_data["processed_dict"]["user"]} added to lms')
        api_data = json.loads(resp.content.decode('utf-8'))
        self.single_user_data['processed_dict']['new_usr_request'] = api_data
        self.single_user_data['processed_dict']['group_membership_dict']['lms_id']=api_data.get('id')
        print(api_data)
        print(f"new user: {self.single_user_data['processed_dict'].get('user')}")
    def get_membership_id(self, newhire_group_id):
        '''checks for membership id, which tells us if they are currently in the group to get newhire courses. We want them to be until their first 90 days is up, then we don't want them in the group'''
        url = f"https://dowbuilt.learnupon.com/api/v1/group_memberships?group_id={newhire_group_id}&version_id=1.1"
        headers = CaseInsensitiveDict()
        headers["Content-Type"] = "application/json"
        headers["Authorization"] = f"Basic {self.learnupon_token}"  

        resp = requests.get(url, headers=headers)
        data = json.loads(resp.content.decode('utf-8'))
        membership_id = 'none'  

        for user in data.get('user'):
            if user.get('email') == self.single_user_data['input_dict'].get('work_email'):
                membership_id = user.get('id')

        return membership_id    
    def rmv_from_newhire_group(self, group_membership_dict):
        '''removes user from newhire group b/c they are no longer newhire!'''
        try:
            url = f"https://dowbuilt.learnupon.com/api/v1/group_memberships/{group_membership_dict.get('membership_id')}"
            headers = CaseInsensitiveDict()
            headers["Content-Type"] = "application/json"
            headers["Authorization"] = f"Basic {self.learnupon_token}" 
            resp = requests.delete(url, headers=headers)
            if resp.status_code in [200, 201, 202]:
                newhire_group_delete_status = f'{self.single_user_data["processed_dict"]["user"]} removed from {group_membership_dict.get("newhire_group_title")} group'
                self.log.log(newhire_group_delete_status)
            else:
                newhire_group_delete_status = 'Error w/ removing user from new_hire group'
        except:
            newhire_group_delete_status = 'Error w/ removing user from new_hire group'
        
        return newhire_group_delete_status    
    def add_newhire_to_group(self, group_membership_dict):
        '''puts newhires into the appropriate newhire group (as calculated in python code block above the path split)'''
        try:
            url = "https://dowbuilt.learnupon.com/api/v1/group_memberships"
            headers = CaseInsensitiveDict()
            headers["Content-Type"] = "application/json"
            headers["Authorization"] = f"Basic {self.learnupon_token}"

            json_data = {
                'GroupMembership': {
                    'group_id': group_membership_dict.get('newhire_group_id'),
                    'user_id': group_membership_dict.get('lms_id'),
                }}

            resp = requests.post(url, headers=headers, json=json_data)

            if resp.status_code in [200, 201, 202]:
                newhire_group_status = f'{self.single_user_data["processed_dict"]["user"]} add to {group_membership_dict.get("newhire_group_title")} group'
                self.log.log(newhire_group_status)
            else:
                newhire_group_status = {'error_message': f"Error: Received status code {resp.status_code}. Message: {resp.text}"}

        except requests.RequestException as e:
            newhire_group_status = {'error_message':f"An error occurred while making the request: {e}"}

        except json.JSONDecodeError as e:
            newhire_group_status = {'error_message': f"An error occurred while decoding the JSON: {e}"}

        return newhire_group_status
#endregion

#region python data processing
    def get_current_date_time(self):
        '''fetch today so we have access to date calculations (not native to Zapier I believe)'''
        time_now = datetime.now()
        today = time_now.strftime("%Y-%m-%d %H:%M")
        return today  
    def move_hiredate_back(self):
        '''this moves the hire date back one day to account for hire date triggering a day early sometimes (so filter logic needs to let it through if its one day early)'''
        try:
            hiredate_movedback = (datetime.strptime(self.single_user_data['input_dict'].get('hris_hireDate'), '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')   
        # won't work if Hire Date is blank (0000-00-00), so I give it a hire date in the future which will naturally filter out
        except ValueError:
            fake_date  = datetime.now() + timedelta(days=5)
            hiredate_movedback = fake_date.strftime("%Y-%m-%d %H:%M")
        return hiredate_movedback   
    def transform_employee_number(self):
        '''makes sure all employee number is 6 digit, because at one point they were four numbers and they need to be converted if so'''
        if len(self.single_user_data['input_dict']["hris_uuid"]) == 4:
            hris_uuid = "00" + str(self.single_user_data['input_dict'].get("hris_uuid"))
        else:
            hris_uuid =  str(self.single_user_data['input_dict'].get("hris_uuid"))

        self.single_user_data['input_dict']['six_dig_hris_uuid'] = hris_uuid
    def locate_employee_data(self):
        '''loops through lms data looking for match betwen username and employee id, if found extracts lms id and changes new_user to false'''
        lms_id = "not_found" 
        new_usr = True
        lms_dict="not_found"  
        hris_dict = "Error-- Employee number could not be relocated in BambooHR"

        for usr in self.lms_usr_list.get('user'):
            if usr.get('username') == self.single_user_data['input_dict'].get('six_dig_hris_uuid'):
                lms_id = usr.get('id')
                new_usr = False
                lms_dict = usr
        
        for usr in self.hris_usr_list:
            if usr.get('employeeNumber') == self.single_user_data['input_dict'].get('hris_uuid'):
                hris_dict = usr
        
        return lms_id, new_usr, lms_dict, hris_dict 
    def handle_employee_status(self):
        '''receives employee status in hris and then creates appropriate perameters to either enable user w/ their email, or disable user with fake email'''
        if self.single_user_data['input_dict']["hris_status"] == "Active":
            return True, self.single_user_data['input_dict'].get("work_email")
        else:
            return False, f"{self.single_user_data['input_dict'].get('six_dig_hris_uuid')}emailremoved@fake.com"  
    def get_supervisor_status(self):
        '''checks supervisor status, and then returns peramters that match'''
        if str(self.single_user_data['input_dict'].get("sup")).find("None") != -1:
            return False, "learner" 

        return True, "learner" # Or "manager" if needed 
    def classify_newhire_group(self):
        '''checks their department and job title to see if they should get the normal newhire training, or the ones for employees that do not get hardware or email, returns the group id for the appropriate group'''
        hris_department_lower = self.single_user_data['input_dict'].get('hris_department').lower()
        hris_jobTitle_lower = self.single_user_data['input_dict'].get('hris_jobTitle').lower()

        if hris_department_lower == 'field' and ('super' in hris_jobTitle_lower or 'foreman' in hris_jobTitle_lower):
            return 686282, 'New Hires: Field Crew'  
        else:
            return 686284, 'New Hires (Except Field Crew)'
    def check_after_ninety_days(self, today):
        '''checks if newhire is still within 90 days of being hired'''
        hire_date_obj = datetime.strptime(self.single_user_data['input_dict'].get('hris_hireDate'), '%Y-%m-%d')
        today_obj = datetime.strptime(today, '%Y-%m-%d %H:%M')
        difference = today_obj - hire_date_obj

        return difference.days > 90 
    def assess_newhire_group_membership(self):
        '''checks user meta data. been 90 days? do they have membership ids (proving they are in groups?) hae they started? 
        this set of functions decides what should happen and makes the discrepency so the "user up to date" filter doesn't miss it'''
        group_membership_dict = self.single_user_data['processed_dict']['group_membership_dict']
        membership_id=group_membership_dict.get('membership_id')
        after_ninety_days=group_membership_dict.get('after_ninety_days')
        employee_started_bool = group_membership_dict.get('employee_started_bool')

        # creates discrepency for when script compares HRIS and LMS data to see if user should have updates run
        if membership_id != 'none' and after_ninety_days == True:
            self.single_user_data['hris_dict']['lms_group_title'] = ""
            self.single_user_data['lms_dict']['lms_group_membership_title'] = self.single_user_data['processed_dict']['group_membership_dict'].get('newhire_group_title')
        elif membership_id == 'none' and after_ninety_days == False and employee_started_bool == True:
            self.single_user_data['hris_dict']['lms_group_title'] = self.single_user_data['processed_dict']['group_membership_dict'].get('newhire_group_title')
            self.single_user_data['lms_dict']['lms_group_membership_title'] = ""
        else:
            # make sure fields exist
            self.single_user_data['hris_dict']['lms_group_title'] = ""
            self.single_user_data['lms_dict']['lms_group_membership_title'] = ""   
    def handle_newhire_group_membership(self):
        '''checks user meta data. been 90 days? do they have membership ids (proving they are in groups?) hae they started? 
        if its been 90 days and they are active, remove from group. if its not been 90 days and they dont have a group, (and they are active user) add them to one'''
        newhire_group_status = "not eligible for changes"
        self.single_user_data['processed_dict']['group_membership_dict']['newhire_group_status'] = newhire_group_status
        group_membership_dict = self.single_user_data['processed_dict']['group_membership_dict']
        membership_id=group_membership_dict.get('membership_id')
        after_ninety_days=group_membership_dict.get('after_ninety_days')
        employee_started_bool = group_membership_dict.get('employee_started_bool')


        if membership_id != 'none' and after_ninety_days == True:
            newhire_group_status = self.rmv_from_newhire_group(group_membership_dict)
        elif membership_id == 'none' and after_ninety_days == False and employee_started_bool == True:
            newhire_group_status = self.add_newhire_to_group(group_membership_dict)

        return newhire_group_status
#endregion

#region filter (deciding if particular user should update)
    def run_filter(self):
        '''there are two reasons to filter out a user.
        1. The user is not active user with all fields completed in bambooHR, they have either been termindated or have not started employement yet
        3. The user has complete information (and is active), but its an exact match to what learnupon has in the system, no need to do updates'''
        self.single_user_data['processed_dict']['filters'] = {}
        
        update_needed = self.filterout_uptodate_lmsuser()
        active_user, active_user_message = self.filterout_incomplete_bambuser()
        ss_exempt = self.filterout_ss_exempt()

        self.single_user_data['processed_dict']['filters']['user_uptodate'] = update_needed 
        self.single_user_data['processed_dict']['filters']['user_inactive'] = active_user
        self.single_user_data['processed_dict']['filters']['user_ss_exempt'] = ss_exempt
        self.single_user_data['processed_dict']['filters']['active_user_message'] = active_user_message  
        
        if active_user == False and update_needed == False and ss_exempt == False:
            filtered_out = False
            return filtered_out
        else:
            print(f'{self.single_user_data["processed_dict"].get("user")} got filtered out: ', 
                f'user_inactive: {active_user}',
                f'user_uptodate: {update_needed}',
                f'user_ss_exempt: {ss_exempt}',
                ' (all must be False to continue).'
                )
            filtered_out = True
            return filtered_out
    def filterout_incomplete_bambuser(self):
        '''filters out users that are not active with all fields completed in bambooHR, they have either been termindated (& not in LMS) or have not started employement yet'''

        # Inactive & not in LMS, return False
        if self.single_user_data['lms_dict'] == "not_found" and self.single_user_data['processed_dict']['enabled'] == False:
            return True, "employee terminated, not in LMS"
        # Missing work email, or before starting date, return False
        elif self.single_user_data['processed_dict'].get('work_email') == None or self.single_user_data['processed_dict'].get('employee_started_bool') == False or self.single_user_data['processed_dict'].get("hireDate") == '0000-00-00':
            return True,  "employee hasn't started. Missing work email and/or before start date"
        else:
            return False, "active employee"
    def compare_data(self):
        '''compare LMS and HRIS data to see if an update is needed (by mapping through the fields, comparing values)'''
        # check if the newhire group needs/vs realities, that component is part of comparing data
        self.assess_newhire_group_membership()

        discrepancies = []

        # Mappings from LMS field names to HRIS fields
        mappings = {
            'issupervisor': '-44',  # isSuper mapping
            # 'employeenumber': 'employeeNumber',
            'hiredate': 'hireDate',
            'location': 'location',
            'division': 'division',
            'department': 'department',
            'jobtitle': 'jobTitle',
            'reportingto': '91',  # supervisor name
            'first_name': 'firstName',
            'last_name': 'lastName',
            'email': 'workEmail',
            'username': 'employeeNumber',
            'enabled':'status',
            'lms_group_membership_title':'lms_group_title'
        }
        if self.single_user_data['lms_dict'] != 'not_found':
        # Convert boolean values and check for discrepancies
            for lms_field, hris_field in mappings.items():
                lms_value = self.single_user_data['lms_dict'][lms_field] if lms_field in self.single_user_data['lms_dict'] else self.single_user_data['lms_dict']['CustomData'].get(lms_field)

                hris_value = self.single_user_data['hris_dict'][hris_field]

                # if -44 is 1, issupervisor should be 1, if -44 is None, is supervisor should be 0
                if lms_field == 'issupervisor':
                    if str(hris_value) == "None":
                        hris_value = "0"

                # enabled is True/False, status is Active/Inactive
                if lms_field == 'enabled':
                    if str(hris_value) == "Active":
                        hris_value = "True"
                    else:
                        hris_value = "False"

                # Special condition for 'username' and 'employeeNumber' (that a four digit hris value equals the same in lms with two leading zeros)
                # i.e. 004444 == 4444
                if lms_field == 'username' and len(lms_value) == 6 and lms_value.startswith("00") and lms_value[2:] == hris_value:
                    continue

                # if user is inactive in lms, their email will not be their HRIS email, but a generated one. 
                # if this value matches what python generated, it means there is nothing new to update
                # i.e., Ariel's email != ariel@dowbuilt.com, but == ariel-removed@dowbuilt.com, nothing to update
                if lms_field == 'email':
                    if str(lms_value) == self.single_user_data['processed_dict']['work_email']:
                        continue

                if str(lms_value) != str(hris_value):
                    discrepancies.append({
                        'field': hris_field,
                        'lms_value': lms_value,
                        'hris_value': hris_value
                    })

        else:
            discrepancies = 'new usr, all fields'
        
        self.single_user_data['processed_dict']['lms_fields_needing_update']=discrepancies
    def filterout_uptodate_lmsuser(self):
        ''''Checks to see if user needs fields updating. Produces a boolean, if True will filter user out, if false will let them continue to update'''
        # self.a = self.single_user_data['processed_dict']
        # will fail if XXX_dict == "not found", if that is the case, just let it through as this filter cannot do its job
        try:
            self.compare_data()
        except KeyError:
            return False
        
        if self.single_user_data['processed_dict'].get('lms_fields_needing_update') == []:
            return True
        else:
            return False
    def filterout_ss_exempt(self):
        '''if user email is in the smartsheet exception list (and should be filted out of further updates), return false, else true''' 
        if self.single_user_data['processed_dict'].get('work_email') in self.active_exceptions:
            return True
        else:
            return False
#endregion

#region run commands
    def run_closing_data(self):
        '''closing statistics on the dataset'''
        total = 0
        filtered_out = 0
        for user_data in self.all_user_data:
            total = total + 1
            if user_data['processed_dict']['filters']['filtered_out'] == True:
                filtered_out = filtered_out + 1
        self.log.log(f"script ran for {total - filtered_out}/{total} employees (the rest were filtered out)")
        self.log.log(f"Script COMPLETED")
        self.log.ss_log()
    def handle_data_processing(self):
        '''runs for single employee. First few variables are for all users, and then the rest are only for active users. 
        inactive users will have less metadata, but we need to grab enough to see they are inactive and give them an email based on their employee number'''
        # create fields with simple values
        self.single_user_data['processed_dict'] = 'processing...'
        self.single_user_data['hris_dict'] = "not_found"
        self.single_user_data['lms_dict'] = "not_found"

        # grab fundimental data
        usr = f"{self.single_user_data['input_dict'].get('hris_first')} {self.single_user_data['input_dict'].get('hris_last')}"
        hris_uuid = self.transform_employee_number()
        enabled, work_email = self.handle_employee_status()
        today = self.get_current_date_time()
        hiredate_movedback = self.move_hiredate_back()
        employee_started_bool = today >= hiredate_movedback
        
        # grab the rest of the processing data
        try:
            # raise Exception("Manually triggered exception.")
            lms_id, new_usr, lms_dict, hris_dict = self.locate_employee_data()
            isSupervisor, user_type = self.get_supervisor_status()
            newhire_group_id, newhire_group_title = self.classify_newhire_group()
            after_ninety_days = self.check_after_ninety_days(today)
            membership_id = self.get_membership_id(newhire_group_id)
            group_membership_dict={'membership_id': membership_id, 'after_ninety_days':after_ninety_days, 'newhire_group_id':newhire_group_id, 'newhire_group_title':newhire_group_title, 'employee_started_bool':employee_started_bool, 'lms_id':lms_id}
            python_returns = {
                'user': usr,
                'enabled': enabled, 
                'work_email': work_email,
                'today': today,
                'hiredate_movedback':hiredate_movedback,
                'employee_started_bool':employee_started_bool,
                'id': hris_uuid, 
                'lms_id': lms_id,
                'new_usr': new_usr, 
                'isSupervisor': isSupervisor, 
                'user_type': user_type,
                'group_membership_dict':group_membership_dict,
                'filters':{}
            }
        
        # return only fundimental data if we cannot find user in hris dict or lms dict
        except:
            python_returns = {
                'user': usr,
                'enabled': enabled, 
                'work_email': work_email,
                'today': today,
                'hiredate_movedback':hiredate_movedback,
                'employee_started_bool':employee_started_bool,
                'filters':{}
            }   
        self.single_user_data['processed_dict'] = python_returns
        self.single_user_data['hris_dict'] = hris_dict
        self.single_user_data['lms_dict'] = lms_dict     
    def run(self):
        '''runs main script as intended
        creates a self.sing_user_data per employee, these have four keys, input dict, processed dict, hris_dict (info on them in bamboohr), lms_dict (info on them in lms). 
        first it collects all this information, then it acts on it.'''
        self.pull_hris_users()
        self.pull_lms_users()
        self.pull_ss_exemptions()
        self.all_user_data = []
        for index, employee in enumerate(self.hris_usr_list):
            if self.dev == True:
                if employee.get('employeeNumber') == '4440' or employee.get('employeeNumber') == '4444': 
                # or employee.get('employeeNumber') == '4444':
                    self.single_user_data = {}
                    self.setup_inputs(employee)
                    self.handle_data_processing()
                    filtered_out = self.run_filter()
                    self.single_user_data['processed_dict']['filters']['filtered_out'] = filtered_out
                    self.all_user_data.append(self.single_user_data)
                    if filtered_out == False:
                        if self.single_user_data['processed_dict'].get('new_usr') == True:
                            # print('new')
                            self.new_lms_user()
                            self.single_user_data['processed_dict']['group_membership_dict']['newhire_group_status'] = self.handle_newhire_group_membership()
                        elif self.single_user_data['processed_dict'].get('new_usr') == False:
                            # print('update')
                            self.update_lms_user()
                            self.single_user_data['processed_dict']['group_membership_dict']['newhire_group_status'] = self.handle_newhire_group_membership()
        self.run_closing_data()
#endregion

if __name__ == "__main__":
    config = {
        'smartsheet_token':smartsheet_token,
        'bamb_token':bamb_token,
        'learnupon_token':learnupon_token,
        'learnupon_basicauth':learnupon_basicauth,
        'bamb_token_base64':bamb_token_base64,
        'dev':False
    }
    dev_config = {
        'smartsheet_token':smartsheet_token,
        'bamb_token':dev_bamb_token,
        'learnupon_token':learnupon_token,
        'learnupon_basicauth':learnupon_basicauth,
        'bamb_token_base64':dev_bamb_token_base64,
        'dev':True
    }
    lu = LmsUpdater(dev_config)
    lu.run()

# TODO: hook up tests 
# // create mailchimp-esque logging system 
# // creating server-side logging sytem 
# // server-side deploy
# figure out groups!

# test that inactive user don't break compare data stuff
# check to see if user needs to be rmv'd from OTHER group