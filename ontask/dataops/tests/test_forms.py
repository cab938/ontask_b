# -*- coding: utf-8 -*-

"""Test form error detection."""
import os

from django.conf import settings
from rest_framework import status

from ontask import tests


class DataopsTestFormErrorsEmptyWorkflow(tests.OnTaskTestCase):
    """Test the form error detection."""

    fixtures = ['empty_wflow']

    user_email = 'instructor01@bogus.com'
    user_pwd = 'boguspwd'

    workflow_name = 'wflow1'

    def test_csv_upload(self):
        """Test the CSV upload."""
        # Get the regular form
        resp = self.get_response('dataops:csvupload_start')
        self.assertTrue(status.is_success(resp.status_code))

        # POST the data
        filename = os.path.join(
            settings.BASE_DIR(),
            'ontask',
            'fixtures',
            'simple.csv',
        )
        with open(filename) as fp:
            resp = self.get_response(
                'dataops:csvupload_start',
                method='POST',
                req_params={
                    'data_file': fp,
                    'skip_lines_at_top': -1,
                    'skip_lines_at_bottom': 0})
            self.assertNotEqual(resp.status_code, status.HTTP_302_FOUND)

            resp = self.get_response(
                'dataops:csvupload_start',
                method='POST',
                req_params={
                    'data_file': fp,
                    'skip_lines_at_top': 0,
                    'skip_lines_at_bottom': -1})
            self.assertNotEqual(resp.status_code, status.HTTP_302_FOUND)

    def test_google_sheet_upload(self):
        """Test the Google Sheet upload."""
        # Get the regular form
        resp = self.get_response('dataops:googlesheetupload_start')
        self.assertTrue(status.is_success(resp.status_code))

        # POST the data
        filename = os.path.join(
            settings.BASE_DIR(),
            'ontask',
            'fixtures',
            'simple.csv',
        )
        resp = self.get_response(
            'dataops:googlesheetupload_start',
            method='POST',
            req_params={
                'google_url': 'file://' + filename,
                'skip_lines_at_top': -1,
                'skip_lines_at_bottom': 0})
        self.assertNotEqual(resp.status_code, status.HTTP_302_FOUND)
        resp = self.get_response(
            'dataops:googlesheetupload_start',
            method='POST',
            req_params={
                'google_url': 'file://' + filename,
                'skip_lines_at_top': 0,
                'skip_lines_at_bottom': -1})
        self.assertNotEqual(resp.status_code, status.HTTP_302_FOUND)

    def test_s3_upload(self):
        """Test the S3 upload."""
        # Get the regular form
        resp = self.get_response('dataops:s3upload_start')
        self.assertTrue(status.is_success(resp.status_code))

        # POST the data
        filepath = os.path.join(
            settings.BASE_DIR(),
            'ontask',
            'fixtures','simple.csv')
        resp = self.get_response(
            'dataops:s3upload_start',
            method='POST',
            req_params={
                'aws_bucket_name': filepath.split('/')[1],
                'aws_file_key': '/'.join(filepath.split('/')[2:]),
                'skip_lines_at_top': -1,
                'skip_lines_at_bottom': 0,
                'domain': 'file:/'})
        self.assertNotEqual(resp.status_code, status.HTTP_302_FOUND)
        resp = self.get_response(
            'dataops:s3upload_start',
            method='POST',
            req_params={
                'aws_bucket_name': filepath.split('/')[1],
                'aws_file_key': '/'.join(filepath.split('/')[2:]),
                'skip_lines_at_top': 0,
                'skip_lines_at_bottom': -1,
                'domain': 'file:/'})
        self.assertNotEqual(resp.status_code, status.HTTP_302_FOUND)
