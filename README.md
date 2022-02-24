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

`python3 create.py uk 4 5 2021-12-03` where argument 1 is the scope [uk|xi], argument 2 is the start index (1st digit of comm code) and argument 3 is the end index  (1st digit of comm code); arguments 2 and 3 are optional.
