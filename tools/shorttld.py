import itertools

# Generate all 2-character combinations of a-z and 0-9
characters = 'abcdefghijklmnopqrstuvwxyz'#0123456789'
combinations = [''.join(pair) for pair in itertools.product(characters, repeat=2)]

# Append the TLD ".sn" to each combination
domains = [combo + '.ci' for combo in combinations]

# Write the domains to checkthis.txt
with open('checkthis.txt', 'w') as file:
    for domain in domains:
        file.write(domain + '\n')