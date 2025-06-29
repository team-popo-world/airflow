from datetime import datetime, timedelta
from airflow import DAG
from airflow.providers.docker.operators.docker import DockerOperator

# 기본 DAG 설정
default_args = {
    'owner': 'scenario-team',
    'depends_on_past': False,
    'start_date': datetime(2025, 6, 13),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

dag = DAG(
    'scenario_generation_pipeline_docker',
    default_args=default_args,
    description='시나리오 생성 및 전송 파이프라인 (DockerOperator)',
    schedule_interval='0 9 * * *',
    catchup=False,
    tags=['scenario', 'generation', 'json'],
)

IMAGE_NAME = "hwpar0826/scenario_app:latest"  # ← 실제 이미지명으로 교체

# 호스트 <-> 컨테이너 공유 볼륨
VOLUME_MAP = [
    '/home/ubuntu/scenario_shared/news_json_files:/app/news_json_files',
    '/home/ubuntu/scenario_shared/result_json_files:/app/result_json_files'
]

# 1. 결과파일 삭제용 clean task (컨테이너에 clean_files.py 필요)
clean_task = DockerOperator(
    task_id='clean_json_files',
    image=IMAGE_NAME,
    command="python clean_files.py",   # 또는 main.py에 clean 기능이 있으면 해당 명령
    volumes=VOLUME_MAP,
    auto_remove=True,
    dag=dag,
    do_xcom_push=False,
)

# 2. 각 테마별 시나리오 생성 Task
themes = ['pig', 'food', 'magic', 'moon']
generation_tasks = []
for theme in themes:
    task = DockerOperator(
        task_id=f'generate_{theme}_scenarios',
        image=IMAGE_NAME,
        command=f"--theme {theme} --n 1",
        volumes=VOLUME_MAP,
        auto_remove=True,
        dag=dag,
        do_xcom_push=False,
    )
    generation_tasks.append(task)

# 3. 시나리오 전송 Task (send_data.py 실행)
send_task = DockerOperator(
    task_id='send_scenarios',
    image=IMAGE_NAME,
    command="python send_data.py",
    volumes=VOLUME_MAP,
    auto_remove=True,
    dag=dag,
    do_xcom_push=False,
)

# 4. Task 의존성
clean_task >> generation_tasks[0] >> generation_tasks[1] >> generation_tasks[2] >> generation_tasks[3] >> send_task
