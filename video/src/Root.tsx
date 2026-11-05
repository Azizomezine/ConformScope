import {Composition} from 'remotion';
import {DEMO, DemoCut} from './DemoCut';
import {HandCheck, HAND_CHECK_DURATION} from './HandCheck';
import {Intro, INTRO_DURATION} from './Intro';
import {Problem, PROBLEM_DURATION} from './Problem';
import {Final, FINAL_DURATION} from './Final';

export const RemotionRoot: React.FC = () => (
  <>
    {/* Full-screen version, solid navy background. */}
    <Composition
      id="Problem"
      component={Problem}
      durationInFrames={PROBLEM_DURATION}
      fps={30}
      width={1920}
      height={1080}
      defaultProps={{overlay: false}}
    />
    {/* Same scene with a transparent background, to lay over your B-roll. */}
    <Composition
      id="ProblemOverlay"
      component={Problem}
      durationInFrames={PROBLEM_DURATION}
      fps={30}
      width={1920}
      height={1080}
      defaultProps={{overlay: true}}
    />
    {/* Section 3: the check by hand, and the mistake set in concrete. */}
    <Composition id="HandCheck" component={HandCheck} durationInFrames={HAND_CHECK_DURATION} fps={30} width={1920} height={1080} />
    {/* Section 4 → 5: name, then a wipe into the screen recording. */}
    <Composition id="Intro" component={Intro} durationInFrames={INTRO_DURATION} fps={30} width={1920} height={1080} />
    {/* Section 5: the screen recording with punch-ins (DEMO.md). */}
    <Composition id="DemoCut" component={DemoCut} durationInFrames={DEMO.seconds * 30} fps={30} width={1920} height={1080} />
    {/* The submission film: hook, match cut, problem, live demo. */}
    <Composition id="Final" component={Final} durationInFrames={FINAL_DURATION} fps={30} width={1920} height={1080} />
  </>
);
