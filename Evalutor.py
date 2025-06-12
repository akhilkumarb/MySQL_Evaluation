import os

import mysql.connector

import zipfile

import sqlparse

import json

import re

from dotenv import dotenv_values

from openpyxl import Workbook

import logging

import pandas as pd

from backend.config import AUTHOR_PATH, SUBMISSION_PATH


 

log_dir = 'logfile'

os.makedirs(log_dir, exist_ok=True)


 

logging.basicConfig(

    filename=os.path.join(log_dir, 'execution.log'),

    level=logging.INFO,

    format='%(asctime)s - %(levelname)s - %(message)s'

)


 

def get_routine_type_and_name(sql):

    """Extracts whether it's a procedure or function, and the name."""

    match = re.search(r'CREATE\s+(PROCEDURE|FUNCTION)\s+`?(\w+)`?', sql, re.IGNORECASE)

    if match:

        return match.group(1).upper(), match.group(2)

    return None, None


 

def write_parameters_to_file(cursor, db_name, routine_name, output_file, is_author=False):

    """Queries INFORMATION_SCHEMA.PARAMETERS and writes results to a file."""

    query = f"""

    SELECT PARAMETER_NAME, PARAMETER_MODE, DATA_TYPE, DTD_IDENTIFIER

    FROM INFORMATION_SCHEMA.PARAMETERS

    WHERE SPECIFIC_SCHEMA = %s AND SPECIFIC_NAME = %s

    ORDER BY ORDINAL_POSITION;

    """

    cursor.execute(query, (db_name, routine_name))

    rows = cursor.fetchall()

    param_list = []


 

    for row in rows:

        param_name, param_mode, data_type, dtd_identifier = row

   

        if param_name is None:

            continue

       

        param_dict = {

            "mode": param_mode or "IN",  

            "name": param_name,

            "type": dtd_identifier or data_type

        }

        param_list.append(param_dict)

   

    if is_author:

        with open(output_file, 'w') as f:

            f.write(f"{routine_name}\n")

            if not param_list:

                f.write("  (No parameters found)\n")

            for param in param_list:

                f.write(f"{param['mode']} {param['name']} {param['type']}\n")


 

    return param_list



 

def extract_parameters(row, max_params=10):

    params = []

    for i in range(1, max_params + 1):

        mode = row.get(f'Param Mode {i}')

        name = row.get(f'Param Name {i}')

        dtype = row.get(f'Param Type {i}')

        if pd.notna(mode) and pd.notna(dtype):

            params.append({

                "mode": mode,

                "name": name if pd.notna(name) else None,

                "type": dtype

            })

    return params



 

def write_to_json():


 

    func_df = pd.read_excel(f"{AUTHOR_PATH}/Testcases/testcases.xlsx", sheet_name="function_tests")

    proc_df = pd.read_excel(f"{AUTHOR_PATH}/Testcases/testcases.xlsx", sheet_name="procedure_tests")


 

    fun_metadata = {

        "routine_name": func_df.iloc[0]['Routine Name'],

        "routine_name_marks": int(func_df.iloc[0]['Routine Name Marks']),

        "routine_type": func_df.iloc[0]['Routine Type'],

        "routine_type_marks": int(func_df.iloc[0]['Routine Type Marks']),

        "parameters_marks": int(func_df.iloc[0]['Parameters Marks']),

        "return_type": func_df.iloc[0].get('Return Type', None),

        "return_type_marks": int(func_df.iloc[0].get('Return Type Marks', 0)),

        "parameters": extract_parameters(func_df.iloc[0])

    }


 

    fun_tests = []

    for _, row in func_df.iterrows():

        fun_tests.append({

            "function_call": row['Function Call'],

            "marks": int(row['Marks'])

        })


 

    fun_output = {

        "meta_data": fun_metadata,

        "tests": fun_tests

    }


 

    proc_metadata = {

        "routine_name": proc_df.iloc[0]['Routine Name'],

        "routine_name_marks": int(proc_df.iloc[0]['Routine Name Marks']),

        "routine_type": proc_df.iloc[0]['Routine Type'],

        "routine_type_marks": int(proc_df.iloc[0]['Routine Type Marks']),

        "parameters_marks": int(proc_df.iloc[0]['Parameters Marks']),

        "parameters": extract_parameters(proc_df.iloc[0])

    }


 

    proc_tests = []

    for _, row in proc_df.iterrows():

        checks = []

        for i in range(1, 10):

            qcol = f'Check Query {i}'

            mcol = f'Check Marks {i}'

            if qcol in row and pd.notna(row[qcol]):

                checks.append({

                    "query": row[qcol],

                    "marks": int(row[mcol]) if pd.notna(row[mcol]) else 0

                })

        proc_tests.append({

            "procedure_call": row['Procedure Call'],

            "marks": int(row['Marks']),

            "checks": checks

        })


 

    proc_output = {

        "meta_data": proc_metadata,

        "tests": proc_tests

    }


 

    with open(f"{AUTHOR_PATH}/Testcases/fun_testcases.json", "w") as f:

        json.dump(fun_output, f, indent=4)


 

    with open(f"{AUTHOR_PATH}/Testcases/proc_testcases.json", "w") as f:

        json.dump(proc_output, f, indent=4)


 

    print("✅ Updated JSON files created successfully!")



 

def log_with_indent(log_file, text, indent_level=0):

   indent = '  ' * indent_level

   for line in text.split('\n'):

       log_file.write(f"{indent}{line}\n")


 

def normalize_result(rows):

    if not rows:

        return None

    return sorted([list(row) for row in rows])


 

def write_results_to_excel(Solutions_dir, output_file="Trainees_marks.xlsx"):

    result = compare_outputs()

    marks_dict = dict(dotenv_values(".env"))

    all_queries = set()

    for queries in result.values():

        all_queries.update(queries.keys())

    sorted_queries = sorted(list(all_queries))

    wb = Workbook()

    ws = wb.active

    ws.title = "Trainee Results"

    header = ["Trainee ID"] + [f"{query}_res" for query in sorted_queries]+["Fun_avg_marks"]

    ws.append(header)

    for trn_id in result.keys():

        row = [trn_id]

        for query in sorted_queries:

            if result[trn_id][query]==1:

                result[trn_id][query] = marks_dict[query]

            else:

                result[trn_id][query] = 0

            row.append(result[trn_id][query])


 

        fun_output_path = os.path.join(Solutions_dir, trn_id, "fun_output.json")

        total_marks = 0

        num_testcases = 0


 

        if os.path.exists(fun_output_path):

            with open(fun_output_path, 'r') as f:

                fun_output = json.load(f)

                for test_case in fun_output:

                    num_testcases += 1

                    total_marks += int(test_case.get("marks", 0))

        else:

            logging.warning(f"{fun_output_path} not found for {trn_id}")

            print(f"Warning: {fun_output_path} not found for {trn_id}")


 

        avg_marks = round(total_marks / num_testcases, 2) if num_testcases > 0 else 0.0

        row.append(avg_marks)

       

        ws.append(row)

    wb.save(output_file)

    logging.info(f"Excel file '{output_file}' created with trainee results.")

    print(f"Excel file '{output_file}' created with trainee results.")


 

def generate_expected_output(cursor):

    with open(f'{AUTHOR_PATH}/Testcases/fun_testcases.json', 'r') as f:

        json_data = json.load(f)


 

   

    meta_data = json_data.get("meta_data", {})

    test_cases = json_data.get("tests", [])


 

    for case in test_cases:

        call = case['function_call']

        try:

            cursor.execute(call)

            rows = cursor.fetchall()

            result = []

            for row in rows:

                result.append(str(row[0]))

            case["Expected"] = str(result) if result else None

        except Exception as e:

            case['Expected'] = f"Error: {e}"

            print(e)

            logging.error(f"Error generating expected output for function {call}: {e}")


 

         

    updated_data = {

        "meta_data": meta_data,

        "tests": test_cases

    }


 

    with open(f'{AUTHOR_PATH}/Testcases/fun_testcases.json', 'w') as f:

       

        json.dump(updated_data, f, indent = 4)

   

    logging.info("Expected outputs added to fun_testcases.json")

    print("Expected outputs added to fun_tesrcases.json")




 

def generate_procedure_test(cursor):


 



    with open(f'{AUTHOR_PATH}/Testcases/proc_testcases.json', 'r') as f:

        json_data = json.load(f)


 

   

    meta_data = json_data.get("meta_data", {})

    test_cases = json_data.get("tests", [])


 

    for case in test_cases:

        try:

            cursor.execute("START TRANSACTION")

            cursor.execute(case["procedure_call"])

            rows = cursor.fetchall()

            case["Expected"] = normalize_result(rows)


 

            for check in case.get("checks", []):

                try:

                    cursor.execute(check["query"])

                    rows = cursor.fetchall()

                    check["Expected"] = normalize_result(rows)

                except Exception as e:

                    check["Expected"] = f"Error: {e}"


 

            cursor.execute("ROLLBACK")

        except Exception as e:

            cursor.execute("ROLLBACK")

            case["Expected"] = f"Error: {e}"


 

    updated_data = {

        "meta_data": meta_data,

        "tests": test_cases

    }


 

    with open(f'{AUTHOR_PATH}/Testcases/proc_testcases.json', 'w') as f:

        json.dump(updated_data, f, indent=4)


 

    logging.info("Procedure test expected output generated.")




 

def run_trainee_procedures(cursor, mysql_path, trn_id):

    import os, json, sqlparse


 

    proc_path = os.path.join(mysql_path, "proc.txt")

    if not os.path.exists(proc_path):

        return "execute successfully"


 

    output_lines = []

    total_marks = 0


 

    try:

        with open(f'{AUTHOR_PATH}/Testcases/proc_testcases.json', 'r') as f:

            json_data = json.load(f)


 

        meta_data = json_data.get("meta_data", {})

        test_cases = json_data.get("tests", [])


 

        with open(proc_path, 'r') as f:

            content = f.read()


 

        statements = sqlparse.split(content)

        for statement in statements:

            if statement.strip():

                cursor.execute(statement)


 

        routine_type, routine_name = get_routine_type_and_name(content)

        cursor.execute("SELECT DATABASE();")

        db_name = cursor.fetchone()[0]

        params = write_parameters_to_file(cursor, db_name, routine_name, "param_output_file", is_author=False)


 

        output_lines.append("\nMetadata Checks:")


 

        expected_routine_name = meta_data.get("routine_name")

        name_marks = meta_data.get("routine_name_marks", 0)

        if routine_name == expected_routine_name:

            output_lines.append("  Routine Name: Passed")

            output_lines.append(f"  marks: {name_marks}")

            total_marks += name_marks

        else:

            output_lines.append("  Routine Name: Failed")

            output_lines.append(f"    Expected: {expected_routine_name}")

            output_lines.append(f"    Actual:   {routine_name}")


 

        expected_type = meta_data.get("routine_type")

        type_marks = meta_data.get("routine_type_marks", 0)

        if routine_type.upper() == expected_type.upper():

            output_lines.append("  Routine Type: Passed")

            output_lines.append(f"  marks: {type_marks}")

            total_marks += type_marks

        else:

            output_lines.append("  Routine Type: Failed")

            output_lines.append(f"    Expected: {expected_type}")

            output_lines.append(f"    Actual:   {routine_type}")


 

        expected_params = meta_data.get("parameters", [])

        param_marks = meta_data.get("parameters_marks", 0)


 

        def normalize_param(p):

            return {

                "mode": p["mode"].upper(),

                "name": p["name"].lower(),

                "type": p["type"].lower()

            }


 

        expected_normalized = [normalize_param(p) for p in expected_params]

        actual_normalized = [normalize_param(p) for p in params]


 

        if expected_normalized == actual_normalized:

            output_lines.append("  Parameters: Passed")

            output_lines.append(f"  marks: {param_marks}")

            total_marks += param_marks

        else:

            output_lines.append("  Parameters: Failed")

            output_lines.append(f"    Expected: {expected_normalized}")

            output_lines.append(f"    Actual:   {actual_normalized}")


 

        for idx, case in enumerate(test_cases, 1):

            output_lines.append(f"\nTestcase {idx}:")

            proc_call = case["procedure_call"]


 

            try:

                cursor.execute("START TRANSACTION")

                cursor.execute(proc_call)

                rows = cursor.fetchall()

                actual = normalize_result(rows)


 

                expected = case.get("Expected")

                status = "Passed" if actual == expected else "Failed"

                marks_awarded = case.get("marks", 0) if status == "Passed" else 0

                total_marks += marks_awarded

                output_lines.append(f"  Status: {status}")

                output_lines.append(f"  marks: {marks_awarded}")

                if status == "Failed":

                    output_lines.append(f"    Procedure Call: {proc_call}")

                    output_lines.append(f"    Expected: {expected}")

                    output_lines.append(f"    Actual:   {actual}")


 

            except Exception as e:

                cursor.execute("ROLLBACK")

                output_lines.append("  Status: Failed")

                output_lines.append(f"    Procedure Call: {proc_call}")

                output_lines.append(f"    Error: {e}")

                continue


 

            if "checks" in case:

                output_lines.append("  Checks:")

                for check_idx, check in enumerate(case["checks"], 1):

                    try:

                        cursor.execute(check["query"])

                        rows = cursor.fetchall()

                        check_actual = normalize_result(rows)

                        check_expected = check.get("Expected")

                        check_status = "Passed" if check_actual == check_expected else "Failed"

                        marks_awarded = check.get("marks", 0) if check_status == "Passed" else 0

                        total_marks += marks_awarded


 

                        output_lines.append(f"    Check {check_idx}: {check_status}")

                        output_lines.append(f"    marks: {marks_awarded}")

                        if check_status == "Failed":

                            output_lines.append(f"      Query: {check['query']}")

                            output_lines.append(f"      Expected: {check_expected}")

                            output_lines.append(f"      Actual:   {check_actual}")


 

                    except Exception as e:

                        output_lines.append(f"    Check {check_idx}: Failed")

                        output_lines.append(f"      Query: {check['query']}")

                        output_lines.append(f"      Error: {e}")


 

        cursor.execute("ROLLBACK")

        output_lines.append(f"\nTotal marks for procedures: {total_marks}")

        return "\n".join(output_lines)


 

    except Exception as e:

        return f"Error executing procedures: {e}"


 

def run_trainee_functions(cursor, mysql_path, trn_id):

    import os, json, sqlparse, re


 

    fun_path = os.path.join(mysql_path, "fun.txt")

    if not os.path.exists(fun_path):

        return "execute successfully"


 

    output_lines = []

    total_marks = 0

    try:

        with open(f'{AUTHOR_PATH}/Testcases/fun_testcases.json', 'r') as f:

            json_data = json.load(f)


 

        meta_data = json_data.get("meta_data", {})

        test_cases = json_data.get("tests", [])


 

        with open(fun_path, 'r') as f_fun:

            content = f_fun.read()


 

        statements = sqlparse.split(content)

        for statement in statements:

            if statement.strip():

                cursor.execute(statement)


 

        output_lines.append("\nMetadata Checks:")


 

        routine_type, routine_name = get_routine_type_and_name(content)

        cursor.execute("SELECT DATABASE();")

        db_name = cursor.fetchone()[0]

        params = write_parameters_to_file(cursor, db_name, routine_name, "param_output_file", is_author=False)


 

        def normalize_param(p):

            return {

                "mode": p["mode"].upper() if p["mode"] else "IN",

                "name": p["name"].lower() if p["name"] else None,

                "type": p["type"].lower()

            }


 

        expected_routine_name = meta_data.get("routine_name")

        name_marks = meta_data.get("routine_name_marks", 0)

        if routine_name == expected_routine_name:

            output_lines.append("  Routine Name: Passed")

            output_lines.append(f"  marks: {name_marks}")

            total_marks += name_marks

        else:

            output_lines.append("  Routine Name: Failed")

            output_lines.append(f"    Expected: {expected_routine_name}")

            output_lines.append(f"    Actual:   {routine_name}")


 

        expected_type = meta_data.get("routine_type")

        type_marks = meta_data.get("routine_type_marks", 0)

        if routine_type.upper() == expected_type.upper():

            output_lines.append("  Routine Type: Passed")

            output_lines.append(f"  marks: {type_marks}")

            total_marks += type_marks

        else:

            output_lines.append("  Routine Type: Failed")

            output_lines.append(f"    Expected: {expected_type}")

            output_lines.append(f"    Actual:   {routine_type}")


 

        expected_params = meta_data.get("parameters", [])

        param_marks = meta_data.get("parameters_marks", 0)


 

        expected_normalized = [normalize_param(p) for p in expected_params]

        actual_normalized = [normalize_param(p) for p in params]


 

        if expected_normalized == actual_normalized:

            output_lines.append("  Parameters: Passed")

            output_lines.append(f"  marks: {param_marks}")

            total_marks += param_marks

        else:

            output_lines.append("  Parameters: Failed")

            output_lines.append(f"    Expected: {expected_normalized}")

            output_lines.append(f"    Actual:   {actual_normalized}")


 

        expected_return_type = meta_data.get("return_type", "").lower()

        return_type_marks = meta_data.get("return_type_marks", 0)


 

        try:

            cursor.execute(f"SHOW CREATE FUNCTION {routine_name}")

            create_stmt = cursor.fetchone()[2]  

            match = re.search(r"RETURNS\s+([a-zA-Z0-9\(\), ]+)", create_stmt, re.IGNORECASE)

            actual_return_type = match.group(1).strip().lower() if match else "unknown"

        except Exception as e:

            actual_return_type = f"error: {e}"


 

        if expected_return_type == actual_return_type:

            output_lines.append("  Return Type: Passed")

            output_lines.append(f"  marks: {return_type_marks}")

            total_marks += return_type_marks

        else:

            output_lines.append("  Return Type: Failed")

            output_lines.append(f"    Expected: {expected_return_type}")

            output_lines.append(f"    Actual:   {actual_return_type}")


 

        for idx, case in enumerate(test_cases, 1):

            call = case['function_call']

            expected = case.get("Expected")

            try:

                cursor.execute(call)

                rows = cursor.fetchall()

                result = [str(row[0]) for row in rows]

                status = "Passed" if str(result) == expected else "Failed"

            except Exception as e:

                result = f"Error: {e}"

                status = "Failed"


 

            marks_awarded = int(case["marks"]) if status == "Passed" else 0

            total_marks += marks_awarded

            output_lines.append(f"\nTestcase {idx}:")

            output_lines.append(f"  Status: {status}")

            output_lines.append(f"  marks: {marks_awarded}")

            if status == "Failed":

                output_lines.append(f"    Function Call: {call}")

                output_lines.append(f"    Expected: {expected}")

                output_lines.append(f"    Actual:   {result}")


 

        output_lines.append(f"\nTotal marks for functions: {total_marks}")

        return "\n".join(output_lines)


 

    except Exception as e:

        return f"Error executing functions: {e}"


 

def execute_author_queries(cursor):

    with open("logfile/execution.log", 'a') as log_file:


 

        execute_commands(f'{AUTHOR_PATH}/sample_db.txt',cursor,log_file, is_author = True)


 

        os.makedirs(f'{AUTHOR_PATH}/output', exist_ok=True)


 

        queries_dir = f'{AUTHOR_PATH}/queries'

        for query_file in os.listdir(queries_dir):

            if query_file.endswith(".txt"):

                file_path = os.path.join(queries_dir,query_file)

                output_path = os.path.join(f"{AUTHOR_PATH}/output", query_file)

                execute_commands(file_path, cursor,log_file,is_author=True, output_path=output_path)


 

def execute_submissions(cursor):

   solutions_dir = "Solutions"

   os.makedirs(solutions_dir, exist_ok=True)


 

   log_dir = "logfile"

   os.makedirs(log_dir, exist_ok=True)

   log_path = os.path.join(log_dir, "execution.log")


 

   with open(log_path, 'w') as log_file:

       for file in os.listdir(SUBMISSION_PATH):

           if file.endswith(".zip"):

               trn_id = os.path.splitext(file)[0]


 

               log_with_indent(log_file, f"{trn_id}:", 0)


 

               extract_path = os.path.join(SUBMISSION_PATH, f"unzipped_{trn_id}")

               os.makedirs(extract_path, exist_ok=True)


 

               with zipfile.ZipFile(os.path.join(SUBMISSION_PATH, file), 'r') as zip_ref:

                   zip_ref.extractall(extract_path)


 

               mysql_path = os.path.join(extract_path, trn_id, "MySQL")

               trn_solution_path = os.path.join(solutions_dir, trn_id)

               os.makedirs(trn_solution_path, exist_ok=True)


 

               log_with_indent(log_file, "function:", 1)

               try:

                   fun_log = run_trainee_functions(cursor, mysql_path, trn_id)

                   log_with_indent(log_file, fun_log, 2)

               except Exception as e:

                   log_with_indent(log_file, f"Error: {e}", 2)


 

               log_with_indent(log_file, "procedure:", 1)

               try:

                   proc_log = run_trainee_procedures(cursor, mysql_path, trn_id)

                   log_with_indent(log_file, proc_log, 2)

               except Exception as e:

                   log_with_indent(log_file, f"Error: {e}", 2)


 

               for query_file in os.listdir(mysql_path):

                    if query_file.endswith(".txt") and query_file not in ["fun.txt", "proc.txt"]:

                        file_path = os.path.join(mysql_path, query_file)

                        try:

                            log_file.write(f"{query_file}:\n")

                            log_file.flush()

                            execute_commands(file_path, cursor, log_file, is_author=False, trn_id=trn_id)

                        except Exception as e:

                            print(e)


 

               log_with_indent(log_file, "", 0)




 

def compare_outputs():

    author_output = f"{AUTHOR_PATH}/output"

    solution_dir = "Solutions"

    result = {}


 

    author_files = set(os.listdir(author_output))


 

    for trn_id in os.listdir(solution_dir):

       

        trn_path = os.path.join(solution_dir, trn_id)

        comparison = {}


 

        for query_file in os.listdir(trn_path):

            if query_file == "fun_output.json" or query_file == "proc_output.json":

                continue

            sub_file = os.path.join(trn_path, query_file)

            auth_file = os.path.join(author_output, query_file)


 

            with open(auth_file, 'r') as f1, open(sub_file, 'r') as f2:

                is_same = f1.read().strip() == f2.read().strip()

                comparison[query_file] = int(is_same)


 

        result[trn_id] = comparison


 

    return result


 

def execute_commands(file_path, cursor, log_file, is_author=False, output_path=None, trn_id=None):

    file_name = os.path.basename(file_path)

    marks_dict = dict(dotenv_values(f"{AUTHOR_PATH}/.env"))

    with open(file_path, 'r') as file:

        content = file.read()

        statements = sqlparse.split(content)

        author_path = f"{AUTHOR_PATH}/output/"

       

        results = []


 

       

        for statement in statements:

            command = statement.strip()

            if not command:

                continue

            try:

                cursor.execute(command)

                if cursor.with_rows:

                    rows = cursor.fetchall()

                    for row in rows:

                        results.append(str(row))


 

                routine_type, routine_name = get_routine_type_and_name(content)

                if routine_type and routine_name:

                    param_output_file = os.path.join(author_path+file_name)+"params.txt"

                    try:

                        cursor.execute("SELECT DATABASE();")

                        db_name = cursor.fetchone()[0]

                        write_parameters_to_file(cursor, db_name, routine_name, param_output_file, is_author=True)

                    except Exception as e:

                        log_file.write(f"Error fetching parameters for {routine_name}: {e}\n")


 

                if not is_author:

                    check_path = os.path.join(author_path, file_name)

                   

                    try:

                        with open(check_path, 'r') as f:

                            expected = [line.strip() for line in f.readlines()]

                            actual = [str(row) for row in results]

                            status = "Passed" if actual == expected else "Failed"

                            log_file.write(f"   Status: {status}\n")

                            log_file.write(f"    marks: {marks_dict[file_name] if status == "Passed" else 0}\n")


 

                     

                        if status == "Failed":

                            log_file.write(f"    Expected: {expected}\n")

                            log_file.write(f"    Actual: {actual}\n")

                        log_file.flush()

                   

                    except FileNotFoundError as fe:

                        log_file.write(f"check file not found: {check_path}, {fe}\n")

                        log_file.flush()

           

            except Exception as e:

                results.append(f"Error: {e}")

                log_file.write(f" Error: {e}\n")

                log_file.flush()


 

    if output_path:

        with open(output_path, 'w') as f:

            for line in results:

                f.write(line + '\n')


 

def generate_structured_log():

    log_path = os.path.join("logfile", "execution.log")

    solutions_dir = "Solutions"

    author_output_dir = f"{AUTHOR_PATH}/output"


 

    with open(log_path, 'a') as log_file:

        for trn_id in os.listdir(solutions_dir):

            trn_path = os.path.join(solutions_dir, trn_id)

            log_file.write(f"{trn_id}:\n")


 

            fun_file = os.path.join(trn_path, "fun_output.json")

            if os.path.exists(fun_file):

                with open(fun_file) as f:

                    fun_output = json.load(f)

                    passed_all = all(tc.get("Status") == "Passed" for tc in fun_output)

                    if passed_all:

                        log_file.write(f"  function: execute successfully\n")

                    else:

                        log_file.write("  function:\n")

                        for tc in fun_output:

                            if tc.get("Status") != "Passed":

                                log_file.write(f"    call: {tc.get('function_call')}\n")

                                log_file.write(f"      Expected: {tc.get('Excepted')}\n")

                                log_file.write(f"      Actual:   {tc.get('Actual')}\n")

            else:

                log_file.write("  function: No function output found.\n")


 

            proc_file = os.path.join(trn_path, "proc_output.json")

            if os.path.exists(proc_file):

                with open(proc_file) as f:

                    proc_output = json.load(f)

                    passed_all = all(p.get("Status") == "Passed" for p in proc_output)

                    if passed_all:

                        log_file.write(f"  procedure: execute successfully\n")

                    else:

                        log_file.write("  procedure:\n")

                        for p in proc_output:

                            if p.get("Status") != "Passed":

                                log_file.write(f"    procedure_call: {p.get('procedure_call')}\n")

                                log_file.write(f"      Expected: {p.get('Expected')}\n")

                                log_file.write(f"      Actual:   {p.get('Actual')}\n")

                                for chk in p.get("checks", []):

                                    if chk.get("Status") != "Passed":

                                        log_file.write(f"      Check Query: {chk.get('query')}\n")

                                        log_file.write(f"        Expected: {chk.get('Expected')}\n")

                                        log_file.write(f"        Actual:   {chk.get('Actual')}\n")

            else:

                log_file.write("  procedure: No procedure output found.\n")


 

            for query_file in os.listdir(trn_path):

                if query_file.endswith(".txt"):

                    trainee_file = os.path.join(trn_path, query_file)

                    author_file = os.path.join(author_output_dir, query_file)


 

                    log_file.write(f"  {query_file}:\n")

                    if os.path.exists(author_file):

                        with open(trainee_file, 'r') as f1, open(author_file, 'r') as f2:

                            trainee_output = f1.read().strip()

                            author_output = f2.read().strip()

                            if trainee_output == author_output:

                                log_file.write("    execute successfully\n")

                            else:

                                log_file.write("    Expected:\n")

                                log_file.write(f"{author_output}\n")

                                log_file.write("    Actual:\n")

                                log_file.write(f"{trainee_output}\n")

                    else:

                        log_file.write("    Author output not found for comparison.\n")

            log_file.write("\n")


 

           

def main():

    con = None

    cur = None

    try:

        con = mysql.connector.connect(

            host="localhost", user="root", password="root", database="emp"

        )

        if con.is_connected():

            print("Connected")

            cur = con.cursor()

           

            with open('logfile/execution.log', 'w') as f:

                f.write("\n")

            write_to_json()

            execute_author_queries(cur)

            generate_expected_output(cur)

            generate_procedure_test(cur)

            execute_submissions(cur)


 

    except mysql.connector.Error as e:

        logging.error(f"MySQL Error: {e}")

        print(e)


 

    finally:

        if con and cur:

            con.commit()

            cur.close()

            con.close()

            logging.info("Database connection closed.")


 

   

if __name__ == '__main__':

    main()













 
