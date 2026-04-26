import numpy as np
import pickle
from tensorflow.keras.preprocessing.text import Tokenizer
from tensorflow.keras.preprocessing.sequence import pad_sequences
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Embedding, LSTM, Dense, Dropout
from sklearn.preprocessing import LabelEncoder

# sample training data
intents = [
    {'text': 'I spent 100 on food', 'intent': 'add_expense'},
    {'text': 'Paid 500 for transport', 'intent': 'add_expense'},
    {'text': 'Add 2000 shopping expense', 'intent': 'add_expense'},
    {'text': 'Show my expenses', 'intent': 'show_expense'},
    {'text': 'How much did I spend this month?', 'intent': 'show_analysis'},
    {'text': 'Set salary to 5000', 'intent': 'set_salary'},
    {'text': 'Hello', 'intent': 'greeting'},
    {'text': 'Are my expenses okay?', 'intent': 'warning_query'},
]

texts = [i['text'] for i in intents]
labels = [i['intent'] for i in intents]

# preprocessing
max_len = 20

# tokenizer
tokenizer = Tokenizer(oov_token='<OOV>')
tokenizer.fit_on_texts(texts)
sequences = tokenizer.texts_to_sequences(texts)
padded = pad_sequences(sequences, maxlen=max_len, padding='post')

# encode labels
encoder = LabelEncoder()
labels_encoded = encoder.fit_transform(labels)

# model
vocab_size = len(tokenizer.word_index) + 1
model = Sequential()
model.add(Embedding(vocab_size, 16, input_length=max_len))
model.add(LSTM(32))
model.add(Dropout(0.5))
model.add(Dense(32, activation='relu'))
model.add(Dense(len(set(labels)), activation='softmax'))
model.compile(loss='sparse_categorical_crossentropy', optimizer='adam', metrics=['accuracy'])

print('Training model...')
model.fit(padded, np.array(labels_encoded), epochs=200, verbose=1)

# save artifacts
model.save('models/model.h5')
with open('models/tokenizer.pkl', 'wb') as f:
    pickle.dump(tokenizer, f)
with open('models/label_encoder.pkl', 'wb') as f:
    pickle.dump(encoder, f)

print('Model training complete and files saved.')
