"""Phase 3 verification test"""
import sys; sys.path.insert(0, '.')
from datetime import datetime
from src.survey.models import Survey, Question, QuestionOption, QuestionType, SurveyResponse, Answer

# 1. Import test
from src.survey.analysis import DescriptiveAnalyzer, SentimentAnalyzer, WordCloudGenerator, CrossTabAnalyzer, SurveyReportBuilder
print('1. All analysis modules imported OK')

# 2. Descriptive test
q1 = Question(question_id='q1', text='ni man yi ma?', question_type=QuestionType.SINGLE_CHOICE,
              options=[QuestionOption(option_id='a', text='manyi'), QuestionOption(option_id='b', text='bumanyi')])
survey = Survey(survey_id='s1', title='Test Survey', questions=[q1])
responses = [SurveyResponse(response_id=f'r{i}', survey_id='s1',
              answers={'q1': Answer(question_id='q1', answer_value='manyi')},
              completed_at=datetime.now()) for i in range(10)]
responses += [SurveyResponse(response_id=f'r{i}', survey_id='s1',
               answers={'q1': Answer(question_id='q1', answer_value='bumanyi')},
               completed_at=datetime.now()) for i in range(10, 15)]
da = DescriptiveAnalyzer()
result = da.analyze(survey, responses)
assert result['total_responses'] == 15
q1stat = result['per_question']['q1']
assert q1stat['stats']['total_answers'] == 15
print(f'2. Descriptive: {result["total_responses"]} responses, q1={q1stat["stats"]["total_answers"]}')

# 3. Sentiment test
sa = SentimentAnalyzer()
pos = sa.analyze_text('very satisfied, product quality is excellent')
neg = sa.analyze_text('terrible, very disappointed, poor quality')
neu = sa.analyze_text('the weather is nice today')
assert pos['sentiment'] == 'positive', f'Expected positive, got {pos["sentiment"]}'
assert neg['sentiment'] == 'negative', f'Expected negative, got {neg["sentiment"]}'
print(f'3. Sentiment: pos={pos["sentiment"]}({pos["score"]}), neg={neg["sentiment"]}({neg["score"]}), neu={neu["sentiment"]}')

# 4. CrossTab test
q2 = Question(question_id='q2', text='age?', question_type=QuestionType.SINGLE_CHOICE,
              options=[QuestionOption(option_id='a', text='young'), QuestionOption(option_id='b', text='middle')])
survey2 = Survey(survey_id='s2', title='Test', questions=[q1, q2])
resp2 = [SurveyResponse(response_id=f'r{i}', survey_id='s2',
          answers={'q1': Answer(question_id='q1', answer_value='manyi'),
                   'q2': Answer(question_id='q2', answer_value='young')},
          completed_at=datetime.now()) for i in range(5)]
ca = CrossTabAnalyzer()
cr = ca.analyze(survey2, resp2, 'q1', 'q2')
assert 'table' in cr
print(f'4. CrossTab: row={cr["row_question"]}, col={cr["col_question"]}')

# 5. WordCloud test (without jieba)
wcg = WordCloudGenerator()
wc = wcg.generate(['product quality is excellent, service attitude is good', 'reasonable price, worth recommending', 'very satisfied, will continue to use'])
assert wc['total_words'] > 0
print(f'5. WordCloud: {wc["total_words"]} total, {wc["unique_words"]} unique, top={wc["frequencies"][0]["word"] if wc["frequencies"] else "none"}')

# 6. Report builder test
rb = SurveyReportBuilder()
report = rb.build(survey2, resp2, title='Test Report')
assert '# Test Report' in report['report']
print(f'6. Report: {len(report["report"])} chars, contains Q={report["report"].count("Q:")}')

print('=== ALL 6 PHASE 3 TESTS PASSED ===')
