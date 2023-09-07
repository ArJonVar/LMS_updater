import smartsheet
from smartsheet.exceptions import ApiError
from smartsheet_grid import grid
from datetime import datetime, timedelta
import requests
from requests.structures import CaseInsensitiveDict 
import json
import time
from globals import smartsheet_token, bamb_token, learnupon_token, bamb_token_base64
from logger import ghetto_logger

class LmsUpdater():
    '''Explain Class'''
    def __init__(self, config):
        self.config = config
        self.smartsheet_token=config.get('smartsheet_token')
        self.bamb_token=config.get('bamb_token')
        self.learnupon_token=config.get('learnupon_token')
        self.bamb_token_base64=config.get('bamb_token_base64')
        grid.token=smartsheet_token
        self.smart = smartsheet.Smartsheet(access_token=self.smartsheet_token)
        self.smart.errors_as_exceptions(True)
        self.start_time = time.time()
        self.log=ghetto_logger("lms_updater.py")

    def pull_report_512(self):
        '''report 512 has all the parameters designed for this system'''

        url = "https://api.bamboohr.com/api/gateway.php/dowbuilt/v1/reports/512?format=JSON&onlyCurrent=true"
        headers = {"authorization": f"Basic {bamb_token_base64}"}
        response = requests.get(url, headers=headers)
        hris_data=json.loads(response.text).get('employees')
        return hris_data

    def setup_inputs(self, employee):
        '''this code was taken off of Zapier that had a specific system of inputs that I am mirroring here to minimize code changes'''
        e = employee
        input_data = {
            "hris_uuid": e.get('employeeNumber'), 
            'hris_status': e.get('status'),
            'hris_first': e.get('firstName'), 
            'hris_last':e.get('lastName'),
            'sup': e.get('-44'), 
            'work_email': e.get('workEmail'),
            'hris_department': e.get('department'),
            'hris_jobTitle':e.get('jobTitle'),
            'hris_hireDate':e.get('hireDate'),
            'auth_token': self.learnupon_token
        }
        return input_data

#region zapier code block
    def get_current_date_time(self):
        '''fetch today so we have access to date calculations (not native to Zapier I believe)'''
        time_now = datetime.now()
        today = time_now.strftime("%Y-%m-%d %H:%M")
        return today    

    def move_hiredate_back(self, input_data):
        '''this moves the hire date back one day to account for hire date triggering a day early sometimes (so filter logic needs to let it through if its one day early)'''
        hiredate_movedback = (datetime.strptime(input_data['hris_hireDate'], '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')   

        return hiredate_movedback   

    def transform_employee_number(self, input_data):
        '''makes sure all employee number is 6 digit, because at one point they were four numbers and they need to be converted if so'''
        if len(input_data["hris_uuid"]) == 4:
            hris_uuid = "00" + str(input_data["hris_uuid"])
        else:
            hris_uuid =  str(input_data["hris_uuid"])

        return hris_uuid 

    def check_for_new_employee(self, input_data):
        '''tries to fetch data from LMS to see if this is new employee or not (which needs to be handled as post and not put down the line)'''
        try:
            base_url = "https://dowbuilt.learnupon.com/api/v1/users/search?username="
            url = base_url + input_data['hris_uuid']   

            headers = CaseInsensitiveDict()
            headers["Content-Type"] = "application/json"
            headers["Authorization"] = f"Basic {input_data['auth_token']}" # Your authorization token here
            resp = requests.get(url, headers=headers)
            resp_data = json.loads(resp.content.decode('utf-8'))
            lms_id = resp_data.get('user')[0].get('id')
            # self.usr_data= usr_data.get('user')[0].get('id')
            if str(resp_data.get("response_type")) == "ERROR":
                lms_id = "not_found"
        except:
            lms_id = "not_found"  

        if lms_id != "not_found":
            new_usr = False
        else:
            new_usr = True  

        return lms_id, new_usr    

    def handle_employee_status(self, input_data):
        '''receives employee status in hris and then creates appropriate perameters to either enable user w/ their email, or disable user with fake email'''
        if input_data["hris_status"] == "Active":
            return True, input_data["work_email"]
        else:
            return False, f"{input_data['hris_uuid']}emailremoved@fake.com"  

    def get_supervisor_status(self, input_data):
        '''checks supervisor status, and then returns peramters that match'''
        if str(input_data.get("sup")).find("None") == -1:
            return False, "learner" 

        return True, "learner" # Or "manager" if needed 

    def classify_newhire_group(self, input_data):
        '''checks their department and job title to see if they should get the normal newhire training, or the ones for employees that do not get hardware or email, returns the group id for the appropriate group'''
        hris_department_lower = input_data['hris_department'].lower()
        hris_jobTitle_lower = input_data['hris_jobTitle'].lower()

        if hris_department_lower != 'field' or (hris_department_lower == 'field' and (hris_jobTitle_lower.find('super') != -1 or hris_jobTitle_lower.find('foreman') != -1)):
            return 686284, 'not field'
        else:
            return 686282, 'field'  

    def check_after_ninety_days(self, input_data, today):
        '''checks if newhire is still within 90 days of being hired'''
        hire_date_obj = datetime.strptime(input_data['hris_hireDate'], '%Y-%m-%d')
        today_obj = datetime.strptime(today, '%Y-%m-%d %H:%M')
        difference = hire_date_obj - today_obj  

        return difference.days > 90 

    def get_membership_id(self, newhire_group_id, input_data):
        '''checks for membership id, which tells us if they are currently in the group to get newhire courses. We want them to be until their first 90 days is up, then we don't want them in the group'''
        url = f"https://dowbuilt.learnupon.com/api/v1/group_memberships?group_id={newhire_group_id}&version_id=1.1"
        headers = CaseInsensitiveDict()
        headers["Content-Type"] = "application/json"
        headers["Authorization"] = f"Basic {input_data['auth_token']}"  

        resp = requests.get(url, headers=headers)
        data = json.loads(resp.content.decode('utf-8'))
        membership_id = 'none'  

        for user in data.get('user'):
            if user.get('email') == input_data['work_email']:
                membership_id = user.get('id')

        return membership_id    

    def rmv_from_newhire_group(self, input_data, membership_id):
        '''removes user from newhire group b/c they are no longer newhire!'''
        try:
            url = f"https://dowbuilt.learnupon.com/api/v1/group_memberships/{membership_id}"
            headers = CaseInsensitiveDict()
            headers["Content-Type"] = "application/json"
            headers["Authorization"] = f"Basic {input_data['auth_token']}" 
            resp = requests.delete(url, headers=headers)
            data = json.loads(resp.content.decode('utf-8'))
            if data != {}:
                newhire_group_delete_status = 'Error w/ removing user from new_hire group'
            else: 
                newhire_group_delete_status = "Success w/ removing user from new_hire group"
        except:
            newhire_group_delete_status = 'Error w/ removing user from new_hire group'
        
        return newhire_group_delete_status
    
    def add_newhire_to_group(self, input_data, newhire_group_id, lms_id):
        '''puts newhires into the appropriate newhire group (as calculated in python code block above the path split)'''
        try:
            url = "https://dowbuilt.learnupon.com/api/v1/group_memberships"
            headers = CaseInsensitiveDict()
            headers["Content-Type"] = "application/json"
            headers["Authorization"] = f"Basic {input_data['auth_token']}"

            json_data = {
                'GroupMembership': {
                    'group_id': newhire_group_id,
                    'user_id': lms_id,
                }}

            resp = requests.post(url, headers=headers, json=json_data)

            # Check if the request was successful
            if resp.status_code not in [200, 201, 202]:
                return {'error_message': f"Error: Received status code {resp.status_code}. Message: {resp.text}"}

            # Load JSON data from response
            data = json.loads(resp.content.decode('utf-8'))
            return data

        except requests.RequestException as e:
            return {'error_message':f"An error occurred while making the request: {e}"}

        except json.JSONDecodeError as e:
            return {'error_message': f"An error occurred while decoding the JSON: {e}"}

    def handle_newhire_group_membership(self, membership_id, after_ninety_days, input_data, employee_started_bool, newhire_group_id, lms_id):
        '''deletes user's group membership if after 90 days and still in newhire group, adds user to correct new hire group if they ahve been hired, before 90 days and they are not already in a group'''
        newhire_group_status = "not eligible for changes"
        if membership_id != 'none' and after_ninety_days == True:
            # newhire_group_status = self.rmv_from_newhire_group(input_data)
            pass
        elif membership_id == 'none' and after_nintey_days == False and employee_started_bool == True:
            # newhire_group_status = self.add_newhire_to_group(input_data, newhire_group_id, lms_id)
            pass
        return newhire_group_status
#endregion

#region misc 
    def filterout_incomplete_bambuser(self, processed_data):
        '''filters out users that are not active with all fields completed in bambooHR, they have either been termindated or have not started employement yet'''

        if processed_data.get('work_email') != None and processed_data.get('employee_started_bool') != None:
            return True
        else:
            return False

    def filterout_uptodate_lmsuser(self, processed_data):
        ''''explain'''
        return True

#endregion

#region run commands
    def run_update_user(self, processed_data):
        '''explain'''
        print(f"updated user: {processed_data.get('user')}")

    def run_new_user(self, processed_data):
        '''explain'''
        print(f"new user: {processed_data.get('user')}")

    def run_transform_employee_data(self, input_data):
        '''runs for single employee, uses wierd input_data style that comes from zapier'''
        today = self.get_current_date_time()
        hiredate_movedback = self.move_hiredate_back(input_data)
        employee_started_bool = today >= hiredate_movedback
        hris_uuid = self.transform_employee_number(input_data)
        lms_id, new_usr = self.check_for_new_employee(input_data)
        usr = f"{input_data['hris_first']} {input_data['hris_last']}"
        enabled, work_email = self.handle_employee_status(input_data)
        isSupervisor, user_type = self.get_supervisor_status(input_data)
        newhire_group_id, newhire_group_title = self.classify_newhire_group(input_data)
        after_ninety_days = self.check_after_ninety_days(input_data, today)
        membership_id = self.get_membership_id(newhire_group_id, input_data)
        newhire_group_status = self.handle_newhire_group_membership(input_data, membership_id, after_ninety_days, newhire_group_id, employee_started_bool, lms_id)
        python_returns = {
            'today': today,
            'hiredate_movedback':hiredate_movedback,
            'employee_started_bool':employee_started_bool,
            'id': hris_uuid, 
            'lms_id': lms_id,
            'new_usr': new_usr,
            'user': usr, 
            'enabled': enabled, 
            'work_email': work_email,
            'isSupervisor': isSupervisor, 
            'user_type': user_type,
            'newhire_group_id': newhire_group_id,
            'newhire_group_title': newhire_group_title,
            'after_ninety_days': after_ninety_days,
            'newhire_group_status':newhire_group_status
        }
        return python_returns

    def handle_data_transformation(self, input_data):
        '''handles a bunch of cases. Namely, tries to transform the data, 
        and if it hits data it cannot transform or the user is inactive, 
        it saves what it found but ultimately returns 'skip', 
        else reuturns gathered data'''
        skip_message = f"skipped {input_data.get('hris_first')} {input_data.get('hris_last')}, {input_data.get('hris_status')} employee # {input_data.get('hris_uuid')}"
        
        if input_data.get('hris_status') != 'Inactive':
            try:
                result = self.run_transform_employee_data(input_data)
            except Exception as e:
                result = {'error': e, 'message':skip_message}
        else:
            result = {'error':'inactive user', 'message':skip_message}
        
        self.run_data.append(result)
        
        return result

    def run_filter(self, processed_data):
        '''there are two reasons to filter out a user.
        1. The user is not active user with all fields completed in bambooHR, they have either been termindated or have not started employement yet
        3. The user has complete information, but its an exact match to what learnupon has in the system, no need to do updates'''
        complete_user = self.filterout_incomplete_bambuser(processed_data)
        changes_needed = self.filterout_uptodate_lmsuser(processed_data)
        
        if complete_user == True and changes_needed == True:
            filtered_out = False
            return filtered_out
        else:
            print('employee got filtered out, the filters returned the following results: (both must be true to continue): ', 
                f'complete_user: {complete_user}',
                f'changes_needed: {changes_needed}',
                )
            filtered_out = True
            return filtered_out
    def run(self):
        '''runs main script as intended'''
        hris_data = self.pull_report_512()
        self.run_data = []
        for index, employee in enumerate(hris_data):
            if index < 30:
                input_data = self.setup_inputs(employee)
                self.debug = input_data
                processed_data = self.handle_data_transformation(input_data)
                filtered_out = self.run_filter(processed_data)
                if filtered_out == False:
                    if processed_data.get('new_usr') == True:
                        print(processed_data)
                        self.run_new_user(processed_data)
                    elif processed_data.get('new_usr') == False:
                        self.run_update_user(processed_data)
#endregion


if __name__ == "__main__":
    config = {
        'smartsheet_token':smartsheet_token,
        'bamb_token':bamb_token,
        'learnupon_token':learnupon_token,
        'bamb_token_base64':bamb_token_base64
    }
    lu = LmsUpdater(config)
    lu.run()