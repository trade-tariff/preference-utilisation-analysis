import classes.globals as g
import os

file = "test.txt"
msg = "Message"
aws_path = g.app.MEASURES_FILENAME

for i in range(1, 13):
    my_month = str(i).rjust(2, "0")
    date_string = "2021-" + my_month + "-01"
    filename = g.app.MEASURES_FILENAME + "_" + date_string + ".xlsx"
    my_file = os.path.join(os.getcwd(), "_export", date_string, filename)
    aws_path = g.app.MEASURES_FILENAME + "/" + filename

    # Load to AWS
    url = g.app.load_to_aws("Loading file " + date_string, my_file, aws_path)

    # Send the email
    if url is not None:
        subject = "The preference utilisation analysis file for " + date_string
        content = "<p>Hello</p><p>Preference utilisation analysis file for " + date_string + \
            " has been uploaded to this location:</p><p>" + url + "</p><p>Thank you.</p>"
        attachment_list = []
        g.app.send_email_message(subject, content, attachment_list)
