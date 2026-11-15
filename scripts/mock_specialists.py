"""Explicitly synthetic tool decisions shared by offline acceptance scripts."""
import json


def selection_response(payload):
    if payload['tool_choice']['name'] != 'select_route_specialists':
        return None
    capabilities=json.loads(payload['input'][1]['content'])['mission']['capabilities']
    return dict(status='completed',output=[dict(type='function_call',name='select_route_specialists',
        arguments=json.dumps(dict(choices=[dict(agent_id=item['agent_id'],selected=item['configured'],
            reason='Synthetic acceptance selection for available context.' if item['configured'] else 'No configured input.') for item in capabilities])))],
        usage=dict(input_tokens=300,output_tokens=100))
