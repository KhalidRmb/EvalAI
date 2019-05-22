import json
import os
import shutil
import yaml
import tempfile
import zipfile
import copy
import requests
import codecs
import io

from datetime import timedelta
from os.path import join

from django.core.files.uploadedfile import SimpleUploadedFile, TemporaryUploadedFile
from django.core.urlresolvers import reverse_lazy
from django.conf import settings
from django.contrib.auth.models import User
from django.test import override_settings
from django.utils import timezone
import mock

from allauth.account.models import EmailAddress
from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from challenges.models import (
    Challenge,
    ChallengeConfiguration,
    ChallengePhase,
    ChallengePhaseSplit,
    DatasetSplit,
    Leaderboard,
    StarChallenge,
)
from participants.models import Participant, ParticipantTeam
from hosts.models import ChallengeHost, ChallengeHostTeam
from jobs.models import Submission


class CreateChallengeUsingZipFile(APITestCase):
    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)

        self.user = User.objects.create(
            username="host", email="host@test.com", password="secret_password"
        )

        EmailAddress.objects.create(
            user=self.user, email="user@test.com", primary=True, verified=True
        )

        self.challenge_host_team = ChallengeHostTeam.objects.create(
            team_name="Test Challenge Host Team", created_by=self.user
        )

        self.path = join(
            settings.BASE_DIR, "examples", "example1", "test_zip_file"
        )

        self.challenge = Challenge.objects.create(
            title="Challenge Title",
            short_description="Short description of the challenge (preferably 140 characters)",
            description=open(join(self.path, "description.html"), "rb")
            .read()
            .decode("utf-8"),
            terms_and_conditions=open(
                join(self.path, "terms_and_conditions.html"), "rb"
            )
            .read()
            .decode("utf-8"),
            submission_guidelines=open(
                join(self.path, "submission_guidelines.html"), "rb"
            )
            .read()
            .decode("utf-8"),
            evaluation_details=open(
                join(self.path, "evaluation_details.html"), "rb"
            )
            .read()
            .decode("utf-8"),
            creator=self.challenge_host_team,
            published=False,
            enable_forum=True,
            anonymous_leaderboard=False,
            start_date=timezone.now() - timedelta(days=2),
            end_date=timezone.now() + timedelta(days=1),
        )

        with self.settings(MEDIA_ROOT="/tmp/evalai"):
            self.challenge_phase = ChallengePhase.objects.create(
                name="Challenge Phase",
                description=open(
                    join(self.path, "challenge_phase_description.html"), "rb"
                )
                .read()
                .decode("utf-8"),
                leaderboard_public=False,
                is_public=False,
                start_date=timezone.now() - timedelta(days=2),
                end_date=timezone.now() + timedelta(days=1),
                challenge=self.challenge,
                test_annotation=SimpleUploadedFile(
                    open(join(self.path, "test_annotation.txt"), "rb").name,
                    open(join(self.path, "test_annotation.txt"), "rb").read(),
                    content_type="text/plain",
                ),
            )
        self.dataset_split = DatasetSplit.objects.create(
            name="Name of the dataset split",
            codename="codename of dataset split",
        )

        self.leaderboard = Leaderboard.objects.create(
            schema=json.dumps(
                {
                    "labels": ["yes/no", "number", "others", "overall"],
                    "default_order_by": "overall",
                }
            )
        )

        self.challenge_phase_split = ChallengePhaseSplit.objects.create(
            dataset_split=self.dataset_split,
            challenge_phase=self.challenge_phase,
            leaderboard=self.leaderboard,
            visibility=ChallengePhaseSplit.PUBLIC,
        )

        self.zip_file = open(
            join(
                settings.BASE_DIR, "examples", "example1", "test_zip_file.zip"
            ),
            "rb",
        )

        self.test_zip_file = SimpleUploadedFile(
            self.zip_file.name,
            self.zip_file.read(),
            content_type="application/zip",
        )

        self.zip_configuration = ChallengeConfiguration.objects.create(
            user=self.user,
            challenge=self.challenge,
            zip_configuration=SimpleUploadedFile(
                self.zip_file.name,
                self.zip_file.read(),
                content_type="application/zip",
            ),
            stdout_file=None,
            stderr_file=None,
        )
        self.client.force_authenticate(user=self.user)

        self.input_zip_file = SimpleUploadedFile(
            "test_sample.zip",
            b"Dummy File Content",
            content_type="application/zip",
        )

        self.url = reverse_lazy(
            "challenges:create_challenge_using_zip_file",
            kwargs={"challenge_host_team_pk": self.challenge_host_team.pk},
        )

        self.BASE_TEMP_LOCATION = tempfile.mkdtemp()
        self.base_path = join(settings.BASE_DIR, 'tests', 'unit', 'challenges', 'data')

        self.annotation_file_path = join(self.base_path, 'annotations')
        self.challenge_config_yaml_path = join(self.base_path, 'challenge_config.yaml')
        self.altered_challenge_config_yaml_path = join(self.BASE_TEMP_LOCATION, "altered_yaml_file.yaml")
        self.challenge_config_in_txt_format_path = join(self.BASE_TEMP_LOCATION, 'sample.txt')
        self.evaluation_script_file_path = join(self.base_path, 'evaluation_script.zip')

        self.yaml_file = open(join(self.base_path, 'challenge_config.yaml'))
        self.yaml_dict = yaml.safe_load(self.yaml_file)
        self.copy_dict = copy.deepcopy(self.yaml_dict)

        self.alt_file = open(self.altered_challenge_config_yaml_path, 'w+')
        self.alt_file.write("Sample")
        self.alt_file.close()


    def test_create_challenge_using_zip_file_when_zip_file_is_not_uploaded(
        self
    ):
        expected = {"zip_configuration": ["No file was submitted."]}
        response = self.client.post(self.url, {})
        self.assertEqual(response.data, expected)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_challenge_using_zip_file_when_zip_file_is_not_uploaded_successfully(
        self
    ):
        expected = {
            "zip_configuration": [
                "The submitted data was not a file. Check the encoding type on the form."
            ]
        }
        response = self.client.post(
            self.url, {"zip_configuration": self.input_zip_file}
        )
        self.assertEqual(response.data, expected)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_challenge_using_zip_file_when_server_error_occurs(self):
        expected = {
            "error": "A server error occured while processing zip file. Please try again!"
        }
        response = self.client.post(
            self.url,
            {"zip_configuration": self.input_zip_file},
            format="multipart",
        )
        self.assertEqual(response.data, expected)
        self.assertEqual(response.status_code, status.HTTP_406_NOT_ACCEPTABLE)

    def test_create_challenge_using_zip_file_when_challenge_host_team_does_not_exists(
        self
    ):
        url2 = reverse_lazy(
            "challenges:create_challenge_using_zip_file",
            kwargs={
                "challenge_host_team_pk": self.challenge_host_team.pk + 10
            },
        )
        expected = {
            "detail": "ChallengeHostTeam {} does not exist".format(
                self.challenge_host_team.pk + 10
            )
        }
        response = self.client.post(
            url2,
            {"zip_configuration": self.input_zip_file},
            format="multipart",
        )
        self.assertEqual(response.data, expected)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_challenge_using_zip_file_when_user_is_not_authenticated(
        self
    ):
        self.client.force_authenticate(user=None)

        expected = {"error": "Authentication credentials were not provided."}

        response = self.client.post(self.url, {})
        self.assertEqual(list(response.data.values())[0], expected["error"])
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_challenge_using_zip_file_success(self):
        self.assertEqual(Challenge.objects.count(), 1)
        self.assertEqual(DatasetSplit.objects.count(), 1)
        self.assertEqual(Leaderboard.objects.count(), 1)
        self.assertEqual(ChallengePhaseSplit.objects.count(), 1)

        with mock.patch("challenges.views.requests.get") as m:
            resp = mock.Mock()
            resp.content = self.test_zip_file.read()
            resp.status_code = 200
            m.return_value = resp
            response = self.client.post(
                self.url,
                {"zip_configuration": self.input_zip_file},
                format="multipart",
            )
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.assertEqual(Challenge.objects.count(), 2)
        self.assertEqual(DatasetSplit.objects.count(), 2)
        self.assertEqual(Leaderboard.objects.count(), 2)
        self.assertEqual(ChallengePhaseSplit.objects.count(), 2)

    # Helper function for tests below.
    def create_challenge_test_helper(self):
        try:
            exec(self.element_to_delete)
            a = open(self.altered_challenge_config_yaml_path, 'r+')
            yaml.dump(self.copy_dict, a, default_flow_style=False)
        except KeyError: # To catch the case when no element is to be deleted from the yaml file
            pass         # i.e, empty string is passed as key. (Useful for some test cases).

        challengezip = zipfile.ZipFile(join(self.BASE_TEMP_LOCATION,'challenge_zip.zip'), 'w')
        for root, dirs, files in os.walk(self.annotation_file_path):
            for file in files:
                archivename = join('annotation', file)
                challengezip.write(os.path.join(root, file), archivename)

        for f in self.filenames:
            archivename = os.path.split(f)[1]
            challengezip.write(f, archivename)

        challengezip.close()

        with open(join(self.BASE_TEMP_LOCATION,'challenge_zip.zip'), 'rb') as f:

            '''z = SimpleUploadedFile(
                f.name,
                f.read(),
                content_type="application/zip",
            )'''

            expected = {
            'error': self.message
                       }
            response = self.client.post(self.url, {'zip_configuration': f}, format='multipart')
            self.assertEqual(response.data, expected)
            self.assertEqual(response.status_code, self.status_code)
            

    '''def create_challenge_test_helper(self):
        challengezip = zipfile.ZipFile(join(self.base_path, "ziptest.zip"), 'w')
        testtextfile = open(join(self.base_path, 'test.txt'))
        challengezip.write(join(self.base_path, 'test.txt'))
        challengezip.close()
        test_file = open(
            join(self.base_path, "ziptest.zip"),
            "rb",
        )
        z = SimpleUploadedFile(
            test_file.name,
            test_file.read(),
            content_type='application/zip'
            )
        expected = {
            'error': self.message
                       }
        response = self.client.post(self.url, {'zip_configuration': z}, format='multipart')
        self.assertEqual(response.data, expected)'''

    def test_create_challenge_using_zip_file_when_no_yaml_file_present(self):
        self.filenames = [self.evaluation_script_file_path]
        self.message = 'There is no YAML file in zip file you uploaded!'
        self.element_to_delete = "del self.copy_dict['']"
        self.status_code = status.HTTP_406_NOT_ACCEPTABLE
        self.create_challenge_test_helper()

    def test_create_challenge_using_zip_file_when_two_yaml_files_present(self):
        self.filenames = [self.altered_challenge_config_yaml_path, self.challenge_config_yaml_path, self.evaluation_script_file_path]
        self.message = 'There are 2 YAML files instead of one in zip folder!'
        self.element_to_delete = "del self.copy_dict['']"
        self.status_code = status.HTTP_406_NOT_ACCEPTABLE
        self.create_challenge_test_helper()

    def test_create_challenge_using_zip_file_when_eval_script_key_is_missing(self):
        self.filenames = [self.challenge_config_yaml_path, self.evaluation_script_file_path]
        self.message = ('There is no key for evaluation script in YAML file. '
                        'Please add it and then try again!')
        self.element_to_delete = "del self.copy_dict['evaluation_script']"
        self.status_code = status.HTTP_406_NOT_ACCEPTABLE
        self.create_challenge_test_helper()

    def test_create_challenge_using_zip_file_when_no_eval_script_present(self):
        self.filenames = [self.challenge_config_yaml_path]
        self.message = ('No evaluation script is present in the zip file. '
                        'Please add it and then try again!')
        self.element_to_delete = "del self.copy_dict['']"
        self.status_code = status.HTTP_406_NOT_ACCEPTABLE
        self.create_challenge_test_helper()

    def test_create_challenge_using_zip_file_when_no_challenge_phases_key(self):
        self.filenames = [self.challenge_config_yaml_path, self.evaluation_script_file_path]
        self.message = ('No challenge phase key found. '
                        'Please add challenge phases in YAML file and try again!')
        self.element_to_delete = "del self.copy_dict['challenge_phases']"
        self.status_code = status.HTTP_406_NOT_ACCEPTABLE
        self.create_challenge_test_helper()

    def test_create_challenge_using_zip_file_when_no_key_for_test_annotation(self):
        self.filenames = [self.challenge_config_yaml_path, self.evaluation_script_file_path]
        self.message = ('There is no key for test annotation file for'
                       'challenge phase {} in yaml file. Please add it'
                       ' and then try again!'.format(self.yaml_dict[challenge_phases][1][name]))
        self.element_to_delete = "del self.copy_dict['challenge_phases'][1]['test_annotation_file']"
        self.status_code = status.HTTP_406_NOT_ACCEPTABLE
        self.create_challenge_test_helper()

    def test_create_challenge_using_zip_file_when_no_key_for_description(self):
        self.filenames = [self.challenge_config_yaml_path, self.evaluation_script_file_path]
        self.message = ('There is no key for description. '
                        'Please add it and then try again!')
        self.element_to_delete = "del self.copy_dict['description']"
        self.status_code = status.HTTP_406_NOT_ACCEPTABLE
        self.create_challenge_test_helper()

    def test_create_challenge_using_zip_file_when_no_key_for_eval_details(self):
        self.filenames = [self.challenge_config_yaml_path, self.evaluation_script_file_path]
        self.message = ('There is no key for evalutaion details. '
                        'Please add it and then try again!')
        self.element_to_delete = "del self.copy_dict['evaluation_details']"
        self.status_code = status.HTTP_406_NOT_ACCEPTABLE

    def test_create_challenge_using_zip_file_when_no_key_for_TandC(self):
        self.filenames = [self.challenge_config_yaml_path, self.evaluation_script_file_path]
        self.message = ('There is no key for terms and conditions. '
                        'Please add it and then try again!')
        self.element_to_delete = "del self.copy_dict['terms_and_conditions']"
        self.status_code = status.HTTP_406_NOT_ACCEPTABLE
        self.create_challenge_test_helper()

    def test_create_challenge_using_zip_file_when_no_key_for_submission_guidelines(self):
        self.filenames = [self.challenge_config_yaml_path, self.evaluation_script_file_path]
        self.message = ('There is no key for submission guidelines. '
                        'Please add it and then try again!')
        self.element_to_delete = "del self.copy_dict['submission_guidelines']"
        self.status_code = status.HTTP_406_NOT_ACCEPTABLE
        self.create_challenge_test_helper()

    def test_create_challenge_using_zip_file_when_no_key_for_leaderboard(self):
        self.filenames = [self.challenge_config_yaml_path, self.evaluation_script_file_path]
        self.message = ('There is no key \'leaderboard\' '
                        'in the YAML file. Please add it and then try again!')
        self.element_to_delete = "del self.copy_dict['leaderboard']"
        self.status_code = status.HTTP_406_NOT_ACCEPTABLE
        self.create_challenge_test_helper()

    def test_create_challenge_using_zip_file_when_no_key_for_default_order_by_in_lbschema(self):
        self.filenames = [self.challenge_config_yaml_path, self.evaluation_script_file_path]
        self.message = ('There is no \'default_order_by\' key in leaderboard '
                        'schema. Please add it and then try again!')
        self.element_to_delete = "del self.copy_dict['leaderboard'][1]['default_order_by']"
        self.status_code = status.HTTP_406_NOT_ACCEPTABLE
        self.create_challenge_test_helper()

    def test_create_challenge_using_zip_file_when_no_key_for_labels_in_lb_schema(self):
        self.filenames = [self.challenge_config_yaml_path, self.evaluation_script_file_path]
        self.message = ('There is no \'labels\' key in leaderboard '
                        'schema. Please add it and then try again!')
        self.element_to_delete = "del self.copy_dict['leaderboard'][1]['labels']"
        self.status_code = status.HTTP_406_NOT_ACCEPTABLE
        self.create_challenge_test_helper()

    def test_create_challenge_using_zip_file_when_no_key_for_challenge_phase_splits(self):
        self.filenames = [self.challenge_config_yaml_path, self.evaluation_script_file_path]
        self.message = ('There is no key for challenge phase splits. '
                        'Please add it and then try again!')
        self.element_to_delete = "del self.copy_dict['challenge_phase_splits']"
        self.status_code = status.HTTP_406_NOT_ACCEPTABLE
        self.create_challenge_test_helper()

    def test_create_challenge_using_zip_file_when_no_key_for_dataset_splits(self):
        self.filenames = [self.challenge_config_yaml_path, self.evaluation_script_file_path]
        self.message = 'Error in creating challenge. Please check the yaml configuration!'
        self.element_to_delete = "del self.copy_dict['dataset_splits']"
        self.status_code = status.HTTP_400_BAD_REQUEST
        self.create_challenge_test_helper()

    #def test_create_challenge_using_zip_file_when_yaml_syntax_error(self):

    def test_create_challenge_using_zip_file_when_no_test_annotation_file_found(self):
        self.filenames = [self.challenge_config_yaml_path, self.evaluation_script_file_path]
        self.message = ('No test annotation file found in zip file'
                        'for challenge phase \'{}\'. Please add it and '
                        ' then try again!'.format(self.yaml_dict[challenge_phases][1][name]))
        self.element_to_delete = "del self.copy_dict['']"
        self.status_code = status.HTTP_406_NOT_ACCEPTABLE
        self.create_challenge_test_helper()

        shutil.rmtree(BASE_TEMP_LOCATION)

    #def test_create_challenge_using_zip_file_when_some_serializer_error(self):

    #def test_create_challlenge_using_zip_file_when_challenge_is_docker_based(self): #?
        #Make sure that challenge host team is not added as a participant.(?)
