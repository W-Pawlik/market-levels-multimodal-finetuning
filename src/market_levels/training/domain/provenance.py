"""Local experiment progress, separate from the parent's completed schedule."""


def stage_progress(identity, state):
    if 'provenance' not in identity:
        return {}
    return {**identity['provenance'], 'additional_optimizer_steps': state['global_step'],
            'total_training_examples_seen_in_new_stage': state['processed_examples'],
            'cumulative_optimizer_updates_for_reference': 350 + state['global_step']}
