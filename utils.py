import openai
import pandas as pd
import subprocess
import time


def prompt_response(system_prompt, user_prompt):
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "system", "content": f"{system_prompt}"}, {"role": "user", "content": f"{user_prompt}"}],
        temperature=0,
        max_tokens=300,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0,
    )

    response_message = response["choices"][0]["message"]["content"]
    response_message = response_message.replace("\n", " ")

    return response_message


def remove_extra_spaces(line):
    while True:
        line = line.replace("  ", " ")
        if "  " not in line:
            break
    return line.strip()


def heuristic_adjust_spaces(text):
    # Create a set of all the items to check for membership
    first_occurrence_list = [
        "%",
        "&",
        "?",
        "<",
        ">",
        ",",
        ":",
        ";",
        ".",
        "!",
        "^",
        "+",
        "-",
        "/",
        "*",
        "=",
    ]
    second_occurrence_list = ["=", "+", "-", "/", "*", "&"]
    brackets = ["(", ")", "{", "}", "[", "]"]
    # Initialize the output string
    output = ""
    # Initialize the current index to 0
    i = 0
    # Loop over the characters in the text
    while i < len(text):
        # Check if the current character is in the item set
        if text[i] in first_occurrence_list:
            # If it is, add it to the output string with a space on either side

            # If the current character is a '<', check if the next character is also in the item set
            if i + 1 < len(text) and text[i + 1] in second_occurrence_list:
                # If it is, add it to the output string as a single unit with a space on either side
                output += " " + text[i] + text[i + 1] + " "
                # Move the current index forward by two characters
                i += 2
            else:
                output += " " + text[i] + " "
                # Otherwise, move the current index forward by one character
                i += 1
        elif text[i] in brackets:
            output += " " + text[i] + " "
            i += 1
        else:
            # If the current character is not in the item set, add it to the output string
            output += text[i]
            # Move the current index forward by one character
            i += 1
    output = remove_extra_spaces(output)
    # Return the output string
    return output


def heuristic_remove_redundant_words(line):
    redundant_words = ["Refactored code :", "Updated code :", "Fixed code :", "Corrected code :", "```"]
    for reds in redundant_words:
        line = line.replace(reds, "").replace(reds.lower(), "").replace(reds.title(), "")
    return line.strip()


def modify_file_name(file_name, start_index, end_index):
    file_name_parts = file_name.split(".")
    file_name = f"{file_name_parts[0]}_{start_index}_{end_index - 1}.{file_name_parts[1]}"
    return file_name


def write_list_to_file(file_name, list_name, start_index=0, end_index=None):
    if end_index is None:
        end_index = len(list_name)
    file = open(file_name, "w", encoding="UTF-8")
    file.writelines([item + "\n" for item in list_name[start_index:end_index]])
    file.close()


def read_env_file(file_path):
    env_variables = {}
    with open(file_path, "r", encoding="UTF-8") as file:
        for line in file:
            line = line.strip()
            if line and not line.startswith("#"):
                key, value = line.split("=")
                env_variables[key] = value
    return env_variables


def get_env_variable(key, file_path=".env"):
    env_variables = read_env_file(file_path)
    return env_variables.get(key)


def modify_R4R_dataset(buggy_code, target):
    start_focus_tag = "<|startfocus|>"
    end_focus_tag = "<|endfocus|>"
    first_end_point = buggy_code.index(start_focus_tag)
    second_end_point = buggy_code.index(end_focus_tag) + len(end_focus_tag)

    before_context = buggy_code[:first_end_point]
    after_context = buggy_code[second_end_point:]
    output = before_context + target.strip() + after_context

    return output


def get_EM(file1, file2):
    with open(file1, "r", encoding="UTF-8") as f1, open(file2, "r", encoding="UTF-8") as f2:
        refs = f1.readlines()
        preds = f2.readlines()

    count = 0
    matches = []
    for i, (r, p) in enumerate(zip(refs, preds)):
        if r == p:
            count += 1
            matches.append(i)
    print(f"EM: {count / len(refs) * 100}%")
    print(f"matched indices: {matches}")


def read_dataset(dataset_name, source_file_path, target_file_path):
    with open(source_file_path, "r", encoding="UTF-8") as src_file, open(
        target_file_path, "r", encoding="UTF-8"
    ) as tgt_file:
        source_codes = src_file.readlines()
        target_codes = tgt_file.readlines()

    buggy_codes = []
    code_reviews = []
    modified_target_codes = []
    for code, target_code in zip(source_codes, target_codes):
        start_comment_tag = "<|startcomment|>"
        end_comment_tag = "<|endcomment|>"
        end_point = code.index(end_comment_tag) + len(end_comment_tag)

        code_review = code[:end_point].replace(start_comment_tag, "").replace(end_comment_tag, "")
        buggy_code = code[end_point + 1 :].replace("\n", "")

        code_reviews.append(code_review)
        buggy_codes.append(buggy_code)
        if dataset_name == "R4R":
            full_target_code = modify_R4R_dataset(buggy_code, target_code)
            modified_target_codes.append(full_target_code)

    if dataset_name == "tufano":
        return code_reviews, buggy_codes, target_codes
    elif dataset_name == "R4R":
        return code_reviews, buggy_codes, modified_target_codes


def read_raw_tufano_dataset_from_csv(file_path):
    df = pd.read_csv(file_path)
    code_reviews = list(df["comment"])
    code_reviews = [
        code_review.replace("\n", " ").replace("\t", " ").replace("\r", " ") for code_review in code_reviews
    ]
    code_reviews = [remove_extra_spaces(code_review) for code_review in code_reviews]

    buggy_codes = list(df["before_marked"])
    buggy_codes = [
        buggy_code.replace("START", "<START>")
        .replace("END", "<END>")
        .replace("\n", " ")
        .replace("\t", " ")
        .replace("\r", " ")
        for buggy_code in buggy_codes
    ]
    buggy_codes = [remove_extra_spaces(buggy_code) for buggy_code in buggy_codes]

    target_codes = list(df["after"])
    target_codes = [
        target_code.replace("\n", " ").replace("\t", " ").replace("\r", " ") for target_code in target_codes
    ]
    target_codes = [heuristic_adjust_spaces(target_code) for target_code in target_codes]

    # write raw tufano csv file data to text files
    # raw_test_cc_src = [
    #     f"<|startcomment|> {code_review} <|endcomment|> {buggy_code}"
    #     for code_review, buggy_code in zip(code_reviews, buggy_codes)
    # ]
    # write_list_to_file("datasets/tufano/raw_test_CC_src.txt", raw_test_cc_src)
    # write_list_to_file("datasets/tufano/raw_test_CC_tgt.txt", target_codes)

    return code_reviews, buggy_codes, target_codes


def run_python_file(bleu_type, python_file_path, ground_truths_file_path, predictions_file_path, lang="java"):
    # Arguments to pass to the Python file
    arguments = []
    if bleu_type == "BLEU":
        arguments = ["--references", ground_truths_file_path, "--predictions", predictions_file_path]
    elif bleu_type == "CodeBLEU":
        arguments = ["--refs", ground_truths_file_path, "--hyp", predictions_file_path, "--lang", lang]

    try:
        # Run the Python file with arguments
        if bleu_type == "CodeBLEU":
            tree_sitter_build_bash_path = "evaluation/CodeBLEU/parser/build.sh"
            subprocess.run(["bash", tree_sitter_build_bash_path], check=True)
        subprocess.run(["python", python_file_path] + arguments, check=True)
        print("Python file executed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Error while executing Python file: {e}")


def get_predictions_from_openai_and_write_to_file(
    prediction_file_path, ground_truth_path, code_reviews, buggy_codes, target_codes, start_index=0, end_index=None
):
    system_prompt = "You are a coding assistant. You generate only the source code."
    user_command = "Refactor the Buggy Code using the Review without comments"

    prediction_list = []

    test_samples = [i for i in range(start_index, end_index)]

    log_file_name = (
        f"logs/LOGS_{prediction_file_path.split('/')[1].replace('.txt', '')}_{start_index}_{end_index - 1}.txt"
    )
    log_file = open(log_file_name, "w", encoding="UTF-8")

    for i in test_samples:
        try:
            buggy_code = buggy_codes[i]
            code_review = code_reviews[i]
            target_code = target_codes[i]

            user_prompt = f"Buggy Code: {buggy_code}\nReview: {code_review}\n{user_command}"
            prediction = prompt_response(system_prompt, user_prompt)
        except Exception as e:
            print(f"An Exception occurred at sample: {i}. Error details: {str(e)}")
            end_index = i
            break

        # heuristic 1
        prediction = heuristic_adjust_spaces(prediction)
        # heuristic 2
        prediction = heuristic_remove_redundant_words(prediction)
        prediction_list.append(prediction)

        SAMPLE_NO = f"sample: {i}"
        BUGGY_CODE = f"buggy_code: {buggy_code}"
        CODE_REVIEW = f"code_review: {code_review}"
        TARGET_CODE = f"target code: {target_code}"
        PREDICTION = f"response: {prediction}"

        print(SAMPLE_NO)
        print(BUGGY_CODE)
        print(CODE_REVIEW)
        print(TARGET_CODE)
        print(PREDICTION)
        print()

        log_file.write(SAMPLE_NO + "\n")
        log_file.write(BUGGY_CODE + "\n")
        log_file.write(CODE_REVIEW + "\n")
        log_file.write(TARGET_CODE + "\n")
        log_file.write(PREDICTION + "\n")
        log_file.write("\n")

        time.sleep(20)

    prediction_file_path = modify_file_name(prediction_file_path, start_index, end_index)
    ground_truth_path = modify_file_name(ground_truth_path, start_index, end_index)
    # write predictions to a file
    write_list_to_file(file_name=prediction_file_path, list_name=prediction_list)
    # write ground truths to a file
    write_list_to_file(
        file_name=ground_truth_path, list_name=target_codes, start_index=start_index, end_index=end_index
    )
    # calculate BLEU
    run_python_file(
        "BLEU",
        "evaluation/bleu.py",
        prediction_file_path,
        ground_truth_path,
    )
    # calculate CodeBLEU
    run_python_file(
        "CodeBLEU",
        "evaluation/CodeBLEU/calc_code_bleu.py",
        prediction_file_path,
        ground_truth_path,
    )


def transfer_content_to_another_file(keyword, input_file, output_file):
    input = open(input_file, "r", encoding="UTF-8")
    input_lines = input.readlines()

    output_lines = []
    for input_line in input_lines:
        if keyword in input_line:
            output_line = input_line.split(keyword)[1].strip()
            output_lines.append(output_line)

    write_list_to_file(file_name=output_file, list_name=output_lines)
