import yaml
data = yaml.safe_load(open('evals/golden/tasks.yaml'))
print('Total tasks:', len(data['tasks']))
cats = {}
for t in data['tasks']:
    cats[t['category']] = cats.get(t['category'], 0) + 1
print('Categories:', cats)