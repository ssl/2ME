import itertools

# Generate all combinations of three letters from 'a' to 'z'
for letters in itertools.product('abcdefghijklmnopqrstuvwxyz', repeat=1):
    for letters2 in itertools.product('abcdefghijklmnopqrstuvwxyz', repeat=1):
        filename = ''.join(letters) + ''.join(letters)  +'.' + ''.join(letters2) + ''.join(letters2)
        print(filename)
