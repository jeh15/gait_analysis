from absl import app, flags
import os
from enum import Enum
import copy

import jax
import numpy as np

from brax.io import html

from src.envs import unitree_go2_energy_test as unitree_go2
from src.algorithms.ppo.load_utilities import load_policy

jax.config.update("jax_enable_x64", True)

FLAGS = flags.FLAGS
flags.DEFINE_string(
    'checkpoint_name', None, 'Desired checkpoint folder name to load.', short_name='c',
)
flags.DEFINE_integer(
    'checkpoint_iteration', None, 'Desired checkpoint iteration.', short_name='i',
)


class Feet(Enum):
    front_left = 0
    hind_left = 1
    front_right = 2
    hind_right = 3


def main(argv=None):
    # Load from Env:
    velocity_target = 0.375
    phase_targets = [0.25, 0.5, 0.75]

    env = unitree_go2.UnitreeGo2Env(
        velocity_target=velocity_target,
        filename='unitree_go2/scene_mjx.xml',
    )
    reset_fn = jax.jit(env.reset)
    step_fn = jax.jit(env.step)

    # Load Policy:
    make_policy, params = load_policy(
        checkpoint_name=FLAGS.checkpoint_name,
        restore_iteration=FLAGS.checkpoint_iteration,
        environment=env,
    )
    inference_function = make_policy(params)
    inference_fn = jax.jit(inference_function)

    # Initialize Simulation:
    key = jax.random.key(0)

    gaits = []
    key, subkey = jax.random.split(key)
    state = reset_fn(subkey)

    num_steps = 1000
    steady_state_ratio = 0.8
    states = []
    first_contact = []
    contacts = []
    for i in range(num_steps):
        key, subkey = jax.random.split(key)
        action, _ = inference_fn(state.obs, subkey)
        state = step_fn(state, action)
        states.append(state.pipeline_state)

        # Get Steady State:
        steady_state_condition = (
            (i > int((1.0-steady_state_ratio) * num_steps))
            & (i <= int(steady_state_ratio * num_steps))
        )
        if steady_state_condition:
            first_contact.append(state.info['first_contact'])
            contacts.append(state.info['previous_contact'])

    first_contact = np.asarray(first_contact)
    contacts = np.asarray(contacts)

    # Find Start of Stance Indicies for Dominant Foot: [Right Front]
    indicies = np.where(first_contact[:, Feet.front_right.value])[0]
    stride_lengths = np.diff(indicies)

    front_left = []
    hind_right = []
    hind_left = []
    for i in indicies:
        front_left.append(
            np.where(first_contact[i:, Feet.front_left.value])[0][0]
        )
        hind_right.append(
            np.where(first_contact[i:, Feet.hind_right.value])[0][0]
        )
        hind_left.append(
            np.where(first_contact[i:, Feet.hind_left.value])[0][0]
        )

    # Calculate Phases:
    front_left = np.asarray(front_left)[:-1]
    hind_right = np.asarray(hind_right)[:-1]
    hind_left = np.asarray(hind_left)[:-1]

    front_left_phase = front_left / stride_lengths
    hind_right_phase = hind_right / stride_lengths
    hind_left_phase = hind_left / stride_lengths

    # # Account for phase offset: Subtract 1.0
    front_left_phase, hind_right_phase, hind_left_phase = list(
        map(lambda x: np.where(x > 1.0, x - 1.0, x), [front_left_phase, hind_right_phase, hind_left_phase]),
    )

    # Account for phase offset: Modulus
    # front_left_phase, hind_right_phase, hind_left_phase = list(
    #     map(lambda x: np.where(x > 1.0, x % 1, x), [front_left_phase, hind_right_phase, hind_left_phase]),
    # )

    avg_front_left_phase, avg_hind_right_phase, avg_hind_left_phase = list(
        map(lambda x: np.mean(x), [front_left_phase, hind_right_phase, hind_left_phase]),
    )

    # Optimistic Cost: Find closest phase to target:
    avg_phases = [avg_front_left_phase, avg_hind_right_phase, avg_hind_left_phase]
    error = np.sort(avg_phases) - np.asarray(phase_targets)
    cost = np.sum(np.square(error))

    print(f'Front Right Phase: {0.0:.3f} \n Front Left Phase: {avg_front_left_phase:.3f} \n Hind Right Phase: {avg_hind_right_phase:.3f} \n Hind Left Phase: {avg_hind_left_phase:.3f}')
    print(f'Cost: {cost:.3f}')

    # # Generate HTML:
    # html_string = html.render(
    #     sys=env.sys.tree_replace({'opt.timestep': env.step_dt}),
    #     states=states,
    #     height="100vh",
    #     colab=False,
    # )

    # html_path = os.path.join(
    #     os.path.dirname(__file__),
    #     "visualization/visualization.html",
    # )

    # with open(html_path, "w") as f:
    #     f.writelines(html_string)


if __name__ == '__main__':
    app.run(main)
