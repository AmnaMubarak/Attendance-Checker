# Intent: Attendance Checker

## Problem
Attendance records can contain unusual work-hour patterns, inconsistent leave entries, and invalid or missing data. These issues can be difficult to identify manually in a large CSV file.

## Goal
Build a small tool that reads attendance and leave records from a CSV file, identifies unusual patterns, and explains each flag in one sentence.

## Intended user
An HR professional or team manager reviewing employee attendance records.

## Inputs
A CSV containing employee IDs, dates, recorded work hours, scheduled hours, and leave status.

## Outputs
A reviewable table of flagged records, the reason each record was flagged, and a summary of the findings.

## Constraints
- Use Python and Streamlit.
- Validate the input data before analyzing it.
- Make detection thresholds configurable.
- Do not automatically accuse employees of misconduct.
- Do not modify source records.
- Keep all sample employee data fictional.
- Include automated tests and document known limitations.

## Success criteria
The tool runs locally, handles valid and invalid CSV files, identifies expected anomalies in a test dataset, and explains every flag clearly.