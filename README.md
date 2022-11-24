# Preference utilisation analysis

## Implementation steps

- Create and activate a virtual environment, e.g.

  `python3 -m venv venv/`

  `source venv/bin/activate`

- Install necessary Python modules via `pip3 install -r requirements.txt`

## Usage

### To create a new file in Excel format
`python3 create.py uk`

`python3 create.py uk 4 5` where argument 1 is the scope [uk|xi], argument 2 is the start index (1st digit of comm code) and argument 3 is the end index  (1st digit of comm code); arguments 2 and 3 are optional.

`python3 create.py uk 0 10 2022-10-01` where argument 1 is the scope [uk|xi], argument 2 is the start index (1st digit of comm code) and argument 3 is the end index  (1st digit of comm code); arguments 2 and 3 are optional.

## Environment variables

### Data creation

- DATABASE_UK=URI of UK database
- DATABASE_EU=URI of EU database
- WRITE_MEASURES=[0|1] - determines if measures are to be created as part of the generation process

### AWS bucket environment variables

- AWS_ACCESS_KEY_ID=STRING
- AWS_REGION=STRING
- AWS_SECRET_ACCESS_KEY=STRING
- BUCKET_NAME=STRING
- WRITE_TO_AWS=[0|1]

### Send grid mail API
- SENDGRID_API_KEY=STRING
- FROM_EMAIL=STRING
- TO_EMAILS=STRING|STRING|STRING (email|fname|lname)
- SEND_MAIL=[0|1]

### ZIP options
- CREATE_7Z=[0|1]
- CREATE_ZIP=[0|1]
- PASSWORD=STRING
- USE_PASSWORD=[0|1]

### Local debug mode
- DEBUG_OVERRIDE=[0|1]

### Empty descriptions
- PLACEHOLDER_FOR_EMPTY_DESCRIPTIONS=STRING

### Filenames
- MEASURES_FILENAME=STRING
- GEO_FILENAME=STRING