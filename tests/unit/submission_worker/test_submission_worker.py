import os
import shutil

from datetime import timedelta

from django.core.urlresolvers import reverse_lazy
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth.models import User
from django.utils import timezone

from allauth.account.models import EmailAddress
from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from challenges.models import Challenge, ChallengePhase
from hosts.models import ChallengeHostTeam
from jobs.models import Submission
from participants.models import ParticipantTeam, Participant

from scripts.workers.submission_worker import (
	download_and_extract_file,
	download_and_extract_zip_file, 
	create_dir, 
	create_dir_as_python_package, 
	return_file_url_per_environment,
	get_or_create_sqs_queue
	)

from zipfile import ZipFile 

from moto import mock_sqs


class BaseAPITestClass(APITestCase):

    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)

        self.user = User.objects.create(
            username='someuser',
            email="user@test.com",
            password='secret_password')

        EmailAddress.objects.create(
            user=self.user,
            email='user@test.com',
            primary=True,
            verified=True)

        self.user1 = User.objects.create(
            username='someuser1',
            email="user1@test.com",
            password='secret_password1')

        EmailAddress.objects.create(
            user=self.user1,
            email='user1@test.com',
            primary=True,
            verified=True)

        self.challenge_host_team = ChallengeHostTeam.objects.create(
            team_name='Test Challenge Host Team',
            created_by=self.user)

        self.participant_team = ParticipantTeam.objects.create(
            team_name='Participant Team for Challenge',
            created_by=self.user1)

        self.participant = Participant.objects.create(
            user=self.user1,
            status=Participant.SELF,
            team=self.participant_team)

        self.challenge = Challenge.objects.create(
            title='Test Challenge',
            description='Description for test challenge',
            terms_and_conditions='Terms and conditions for test challenge',
            submission_guidelines='Submission guidelines for test challenge',
            creator=self.challenge_host_team,
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=1),
            published=True,
            evaluation_script=
            approved_by_admin=True,
            enable_forum=True,
            anonymous_leaderboard=False)

        os.makedirs('/tmp/evalai')

        with self.settings(MEDIA_ROOT='/tmp/evalai'):
            self.challenge_phase = ChallengePhase.objects.create(
                name='Challenge Phase',
                description='Description for Challenge Phase',
                leaderboard_public=False,
                is_public=True,
                start_date=timezone.now(),
                end_date=timezone.now() + timedelta(days=1),
                challenge=self.challenge,
                test_annotation=SimpleUploadedFile('test_sample_file.txt',
                                                   'Dummy file content', content_type='text/plain')
            )

        self.url = reverse_lazy('jobs:challenge_submission',
                                kwargs={'challenge_id': self.challenge.pk,
                                        'challenge_phase_id': self.challenge_phase.pk})

        self.client.force_authenticate(user=self.user1)

        self.input_file = SimpleUploadedFile(
            "dummy_input.txt", "file_content", content_type="text/plain")

        self.submission = Submission.objects.create(
            participant_team=self.participant_team,
            challenge_phase=self.challenge_phase,
            created_by=self.challenge_host_team.created_by,
            status="submitted",
            input_file=self.input_file,
            method_name="Test Method",
            method_description="Test Description",
            project_url="http://testserver/",
            publication_url="http://testserver/",
            is_public=True,
        )

        BASE_TEMP_DIR = tempfile.mkdtemp()

        zipfile.ZipFile(join(self.BASE_TEMP_LOCATION,'test_zip.zip'), 'w', zipfile.ZIP_DEFLATED)
        z.write(input_file)
        z.close()
        zipfile = SimpleUploadedFile(join(self.BASE_TEMP_LOCATION,'test_zip.zip'), z.read(), content_type='application/zip')

        self.challenge.evaluation_script=zipfile


    def tearDown(self):
        shutil.rmtree('/tmp/evalai')

    def test_download_and_extract_file(self):
    	download_location = os.join(BASE_TEMP_DIR, "test_file.txt")
    	self.url = self.submission.input_file.url
    	download_and_extract_file(self.url, download_location)
    	self.assertTrue(os.path.isfile(download_location))
    	os.remove(download_location)

    def test_download_and_extract_zip_file(self):
    	download_location = os.join(BASE_TEMP_DIR, "zip_download_location.zip")
    	extract_location = os.join(BASE_TEMP_DIR, "zip_extract_location")

    	download_and_extract_zip_file(self.url, download_location, extract_location)
    	self.assertTrue(os.path.isfile(download_location))
    	self.assertTrue(os.path.isfile(os.join(extract_location, "dummy_input.txt")))
    	os.remove(download_location)
    	shutil.rmtree(extract_location)

    def test_create_dir(self):
    	directory = os.join(BASE_TEMP_DIR, "temp_dir")
    	create_dir(directory)
    	self.assertTrue(os.path.isdir(directory))
    	shutil.rmtree(directory)

    def test_create_dir_as_python_package(self):
    	directory = os.join(BASE_TEMP_DIR, "temp_dir")
    	create_dir_as_python_package(directory)
    	self.assertTrue(os.path.isfile(os.join(directory, "__init__.py")))
    	shutil.rmtree(directory)

    def test_return_file_url_per_environment(self):
    	self.url = "/test/url"
    	returned_url = return_file_url_per_environment(self.url)
    	self.assertEqual(returned_url, "http://testserver/test/url")

    @mock_sqs()
    def test_get_or_create_sqs_queue_for_existing_queue(self):
    	client = boto3.client('sqs')
        client.create_queue(QueueName="test_queue")
        queue = get_or_create_sqs_queue("test_queue")
        queue_url = client.get_queue_url(QueueName='test_queue')['QueueUrl']
        self.assertTrue(queue_url)
        client.delete_queue(QueueUrl=queue_url)

    @mock_sqs():
    def test_get_or_create_sqs_queue_for_non_existing_queue(self):
    	client = boto3.client('sqs')
        queue = get_or_create_sqs_queue("test_queue_2")
        client.send_message(
          QueueUrl=self.queue_url,
          MessageBody=message
        )
        queue_url = client.get_queue_url(QueueName='test_queue_2')['QueueUrl']
        self.assertTrue(queue_url)
        client.delete_queue(QueueUrl=queue_url)

