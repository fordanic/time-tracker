interface Props {
  idPrefix: string;
  project: string;
  activity: string;
  projects: string[];
  activities: Record<string, string[]>;
  onProjectChange: (value: string) => void;
  onActivityChange: (value: string) => void;
}

export function ProjectActivityFields({
  idPrefix,
  project,
  activity,
  projects,
  activities,
  onProjectChange,
  onActivityChange,
}: Props) {
  return (
    <>
      <label>
        Project
        <input
          list={`${idPrefix}-project-options`}
          value={project}
          onInput={(event) => onProjectChange(event.currentTarget.value)}
        />
        <datalist id={`${idPrefix}-project-options`}>
          {projects.map((item) => (
            <option key={item}>{item}</option>
          ))}
        </datalist>
      </label>
      <label>
        Activity
        <input
          list={`${idPrefix}-activity-options`}
          value={activity}
          onInput={(event) => onActivityChange(event.currentTarget.value)}
        />
        <datalist id={`${idPrefix}-activity-options`}>
          {(activities[project] ?? []).map((item) => (
            <option key={item}>{item}</option>
          ))}
        </datalist>
      </label>
    </>
  );
}
