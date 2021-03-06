import pytest
import requests

from tests.acceptance.helpers import ENDPOINT_OVERRIDE
from tests.acceptance.helpers import activate_experiment
from tests.acceptance.helpers import create_and_validate_request_and_response
from tests.acceptance.helpers import override_variation


def test_overrides(session_obj):
    """
    Override an experiment decision for a user

    Override a experiment or feature test decision used in future user based decisions.
    This override is only stored locally in memory for debugging and testing purposes
    and should not be used for production overrides.

    Responses from the spec:
        '201':
          description: Forced variation set
        '204':
          description: Forced variation was already set
        '400':
          description: Invalid user id, experiment key, or variation key
        '403':
          $ref: '#/components/responses/Forbidden'

    :param agent_server: starts agent server with default config
    :param session_obj: session fixture

    1. activate experiment and assert "default" variation
    2. force a different variation (override)
    3. activate experiment and assert forced variation is now in place
    4. Try overriding with the same variation again. Should not be possible.
    """
    # Confirm default variation is "variation_1" (activate)
    activating = activate_experiment(session_obj)
    default_variation = activating.json()[0]['variationKey']
    assert activating.status_code == 200, activating.text
    assert default_variation == 'variation_1', activating.text

    # Override with "variation_2"
    resp_over = override_variation(session_obj, override_with='variation_2')
    assert resp_over.status_code == 200, resp_over.text
    assert resp_over.json()['messages'] is None
    assert resp_over.json()['prevVariationKey'] == ''

    # Confirm new variation is "variation_2" (activate)
    activating_again = activate_experiment(session_obj)
    forced_variation = activating_again.json()[0]['variationKey']
    assert activating_again.status_code == 200
    assert forced_variation == "variation_2"

    # Attempt to override variation_2 with the same variation_2. Should be denied (204).
    resp_override_with_same_var = override_variation(session_obj,
                                                     override_with='variation_2')

    assert resp_override_with_same_var.status_code == 200, \
        f'Error: {resp_override_with_same_var.text}'

    assert "updating previous override" in resp_override_with_same_var.json()['messages']
    assert resp_override_with_same_var.json()['prevVariationKey'] == 'variation_2'

    # Delete new variation
    resp_delete = override_variation(session_obj, override_with='')
    assert resp_delete.status_code == 200, resp_delete.text
    assert "removing previous override" in resp_delete.json()['messages']
    assert resp_override_with_same_var.json()['prevVariationKey'] == 'variation_2'

    # Confirm deleting variation_2 caused that the default is now "variation_1" (activate)
    resp_default_now_var_1 = activate_experiment(session_obj)
    default_variation_confirm = activating.json()[0]['variationKey']
    assert resp_default_now_var_1.status_code == 200, activating.text
    assert default_variation_confirm == 'variation_1', activating.text


expected_empty_user = '{"error":"userId cannot be empty"}\n'
expected_empty_experiment_key = '{"error":"experimentKey cannot be empty"}\n'
expected_empty_variation_key = '{"userId":"matjaz","experimentKey":"ab_test1",' \
                               '"variationKey":"","prevVariationKey":"","messages":' \
                               '["no pre-existing override"]}\n'
expected_invalid_user = '{"userId":"invalid_user","experimentKey":"ab_test1",' \
                        '"variationKey":"variation_2","prevVariationKey":"",' \
                        '"messages":null}\n'
expected_invalid_experiment_key = '{"userId":"matjaz","experimentKey":' \
                                  '"invalid_experimentKey","variationKey":"variation_2",' \
                                  '"prevVariationKey":"","messages":' \
                                  '["experimentKey not found in configuration"]}\n'
expected_invalid_variation_key = '{"userId":"matjaz","experimentKey":"ab_test1",' \
                                 '"variationKey":"invalid_variation",' \
                                 '"prevVariationKey":"","messages":' \
                                 '["variationKey not found in configuration"]}\n'


@pytest.mark.parametrize(
    "userId, experimentKey, variationKey, expected_status_code, expected_response, bypass_validation_request", [
        ("", "ab_test1", "variation_2", 400, expected_empty_user, True),
        ("matjaz", "", "variation_2", 400, expected_empty_experiment_key, True),
        ("matjaz", "ab_test1", "", 200, expected_empty_variation_key, False),
        ("invalid_user", "ab_test1", "variation_2", 200, expected_invalid_user, False),
        ("matjaz", "invalid_experimentKey", "variation_2", 200,
         expected_invalid_experiment_key, False),
        ("matjaz", "ab_test1", "invalid_variation", 200, expected_invalid_variation_key, False),
    ], ids=["empty_userId", "empty_experiment_key", "empty_variationKey",
            "invalid_userId", "invalid_experimentKey", "invalid_variationKey"])
def test_overrides__invalid_arguments(session_obj, userId, experimentKey, variationKey,
                                      expected_status_code, expected_response, bypass_validation_request):
    """
    :param session_obj: session object
    :param userId: user id
    :param experimentKey: experiment key
    :param variationKey: variation key
    :param expected_status_code: expected status code in response
    :param expected_response: body of expected response
    :param bypass_validation: option to enable or disable schema validation
    """
    payload = f'{{"userId": "{userId}", ' \
        f'"experimentKey": "{experimentKey}", "variationKey": "{variationKey}"}}'

    resp = create_and_validate_request_and_response(ENDPOINT_OVERRIDE, 'post', session_obj, bypass_validation_request,
                                                    payload=payload)

    assert resp.status_code == expected_status_code, resp.text
    assert resp.text == expected_response


def test_overrides_403(session_override_sdk_key):
    """
    Test that 403 Forbidden is returned. We use invalid SDK key to trigger 403.
    :param session_override_sdk_key: sdk key to override the session using invalid sdk key
    """
    payload = '{"userId": "matjaz",' \
              '"experimentKey": "ab_test1", "variationKey": "my_new_variation"}'

    with pytest.raises(requests.exceptions.HTTPError):
        resp = create_and_validate_request_and_response(ENDPOINT_OVERRIDE, 'post', session_override_sdk_key,
                                                        payload=payload)

        assert resp.status_code == 403
        assert resp.json()['error'] == 'unable to fetch fresh datafile (consider ' \
                                       'rechecking SDK key), status code: 403 Forbidden'

        resp.raise_for_status()
